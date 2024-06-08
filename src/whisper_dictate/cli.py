#!/usr/bin/env python3
import os
import subprocess
import tempfile
import threading
from queue import Queue

import click
import pyperclip
from openai import APIStatusError, OpenAI
from pynput import keyboard
from pynput.keyboard import Controller, Key

FORCE_OPENAI = False

try:
    from whisper_cpp import Whisper
except ImportError:
    print("whisper_cpp not installed, will use OpenAI's API.")
    FORCE_OPENAI = True


# https://github.com/paul-gauthier/aider/blob/03908c5ab64561aed7ce9eac331603215d1dd2ef/aider/voice.py#L68
# https://github.com/paul-gauthier/aider/blob/03908c5ab64561aed7ce9eac331603215d1dd2ef/aider/commands.py#L552



class WhisperDictateException(Exception):
    pass


class WhisperAdapter:
    """
    Adapter that can transcribe either locally with whisper.cpp or using OpenAI's API.
    """

    def __init__(self, model: str, openai=False):
        self.openai = openai or FORCE_OPENAI
        if self.openai:
            self.client = OpenAI()
        else:
            WHISPER_CPP_ROOT = os.environ.get("WHISPER_CPP_ROOT", "")
            if not WHISPER_CPP_ROOT or not os.path.exists(WHISPER_CPP_ROOT):
                raise WhisperDictateException(
                    "`WHISPER_CPP_ROOT` env variable should be set to an existing directory with a"
                    " whisper.cpp installation."
                )

            # Set verbose=False to avoid bug: https://github.com/sphantix/whisper-cpp-pybind/issues/1
            self.whisper = Whisper(
                os.path.join(WHISPER_CPP_ROOT, "models", f"ggml-{model}.bin"), verbose=False
            )

    def transcribe(self, audio_file_path: str, language: str = "auto") -> str:
        prompt = "Use correct capitalization, and commas."
        if self.openai:
            kwargs = {
                "model": "whisper-1",  # only model available so far
                "file": open(audio_file_path, "rb"),
                "prompt": prompt,
            }
            if language != "auto":
                kwargs["language"] = language
            return self.client.audio.transcriptions.create(**kwargs).text

        # Whisper.cpp
        self.whisper.transcribe(
            audio_file_path,
            language=language,
            translate=False,
            prompt=prompt,
        )
        return self.whisper.output(output_txt=True).strip()


def notify(title, text):
    script = f'display notification "{text}" with title "{title}"'
    subprocess.run(["osascript", "-e", script], check=False)


def type_transcript(transcript_content):
    controller = Controller()
    for char in transcript_content:
        if char == "\n":  # If the character is a newline, press Enter
            controller.press(Key.enter)
            controller.release(Key.enter)
        elif char == " ":  # Explicitly handle the space character
            controller.press(Key.space)
            controller.release(Key.space)
        else:
            controller.press(char)
            controller.release(char)


class WhisperDictate:
    def __init__(self, model: str, language: str, paragraphs: bool, openai: bool = False):
        self.recording_process = None
        self.is_recording = False
        self.combination = {
            keyboard.Key.alt_l,
            keyboard.Key.cmd_l,
        }  # Left option and left command keys
        self.current_keys = set()

        self.whisper = WhisperAdapter(model, openai=openai)
        self.language = language
        self.paragraphs = paragraphs

        self.queue = Queue()
        self.consumer_thread = threading.Thread(target=self.process_queue)
        self.consumer_thread.daemon = True
        self.consumer_thread.start()

    def process_queue(self):
        while True:
            audio_file_path = self.queue.get()
            try:
                notify("Processing audio", "Invoking whisper...")
                transcript = self.whisper.transcribe(audio_file_path, language=self.language)

                # Split into paragraph if more coming
                if self.paragraphs and (self.is_recording or not self.queue.empty()):
                    transcript += "\n\n"

                click.secho(transcript, fg="green", bold=True)
                pyperclip.copy(transcript)
                type_transcript(transcript)
            except EOFError as exc:
                notify("Error processing audio", str(exc))
            except APIStatusError as exc:
                notify("Error processing audio", exc.message)
            finally:
                self.queue.task_done()

    def start_recording(self):
        if self.is_recording:
            return

        notify("Recording", "Recording audio for whisper...")

        self.is_recording = True
        self.tmpfile = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)

        self.recording_process = subprocess.Popen(
            [
                "rec",
                "-c",
                "1",  # Number of audio channels (mono)
                "-r",
                "16000",  # Sample rate in Hz
                "-e",
                "signed-integer",  # Sample encoding
                "-b",
                "16",  # Number of bits in each sample
                "-t",
                "wav",  # File type
                self.tmpfile.name,
            ],
            # stdout=subprocess.DEVNULL,
            # stderr=subprocess.DEVNULL,
        )

        print(f"Recording started, temporary file: {self.tmpfile.name}")

    def stop_recording(self):
        if self.is_recording and self.recording_process:
            self.recording_process.terminate()
            self.recording_process.wait()
            self.queue.put(self.tmpfile.name)
            self.is_recording = False

    def on_press(self, key):
        if key in self.combination:
            self.current_keys.add(key)
            if all(k in self.current_keys for k in self.combination):
                self.start_recording()

    def on_release(self, key):
        if key in self.combination:
            self.current_keys.discard(key)
            if not self.current_keys:
                self.stop_recording()


@click.command()
@click.option("-m", "--model", default="medium", show_default=True, help="whisper model to use")
@click.option(
    "-l", "--language", default="auto", show_default=True, help="language for transcription"
)
@click.option(
    "-np",
    "--no-paragraphs",
    is_flag=True,
    default=False,
    show_default=True,
    help="avoid adding line breaks when recording before the last one finished processing",
)
@click.option(
    "--openai",
    is_flag=True,
    default=False,
    show_default=True,
    help="use OpenAI's API instead of local whisper",
)
def main(model, language, no_paragraphs, openai):
    audio_recorder = WhisperDictate(model, language, paragraphs=not no_paragraphs, openai=openai)

    with keyboard.Listener(
        on_press=audio_recorder.on_press, on_release=audio_recorder.on_release
    ) as listener:
        print("Ready! Hold Opt+Left Cmd to dictate.")
        listener.join()


if __name__ == "__main__":
    main()
