#!/usr/bin/env python3
import os
import subprocess
import tempfile
import threading
from queue import Queue

import click
import pyperclip
import whisper_cpp
from pynput import keyboard
from pynput.keyboard import Controller, Key
from whisper_cpp import Whisper


class WhisperDictateException(Exception):
    pass


WHISPER_CPP_ROOT = os.environ.get("WHISPER_CPP_ROOT", "")
if not WHISPER_CPP_ROOT or not os.path.exists(WHISPER_CPP_ROOT):
    raise WhisperDictateException(
        "`WHISPER_CPP_ROOT` env variable should be set to an existing directory with a whisper.cpp"
        " installation."
    )


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
    def __init__(self, model: str, language: str, paragraphs: bool):
        self.recording_process = None
        self.is_recording = False
        self.combination = {
            keyboard.Key.alt_l,
            keyboard.Key.cmd_l,
        }  # Left option and left command keys
        self.current_keys = set()

        # Set verbose=False to avoid bug: https://github.com/sphantix/whisper-cpp-pybind/issues/1
        self.whisper = Whisper(
            os.path.join(WHISPER_CPP_ROOT, "models", f"ggml-{model}.bin"), verbose=False
        )
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

                # Call make_txt_transcript to generate the transcript
                self.whisper.transcribe(
                    # converted_wav_path,
                    audio_file_path,
                    language=self.language,
                    translate=False,
                    prompt="Use correct capitalization, and commas. Keep the original language.",
                )
                transcript = self.whisper.output(output_txt=True).strip()

                # Split into paragraph if more coming
                if self.paragraphs and (self.is_recording or not self.queue.empty()):
                    transcript += "\n\n"

                click.secho(transcript, fg="green", bold=True)
                pyperclip.copy(transcript)
                type_transcript(transcript)
            except EOFError as exc:
                notify("Error processing audio", str(exc))
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
        if self.is_recording:
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
def main(model, language, no_paragraphs):
    audio_recorder = WhisperDictate(model, language, paragraphs=not no_paragraphs)

    with keyboard.Listener(
        on_press=audio_recorder.on_press, on_release=audio_recorder.on_release
    ) as listener:
        print("Ready! Hold Opt+Left Cmd to dictate.")
        listener.join()


if __name__ == "__main__":
    main()