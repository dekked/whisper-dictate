# ✍🏼 Whisper Dictate

Run once. Hold left Opt+Cmd and speak. It will transcribe and type what you said, so you don't have to.

Great multilingual transcription thanks to Whisper, [whisper.cpp](https://github.com/ggerganov/whisper.cpp)!

⚠️ Only tested on macOS, using M1.

## Installation

1. Make sure you have the `rec` command from SoX: `brew install sox`.

2. Install dependencies with poetry: `poetry install`.

3. If you prefer to use local whisper.cpp installation:

   1. Clone [whisper.cpp](https://github.com/ggerganov/whisper.cpp#quick-start).

      1. Download the models you want to use. For best results, `medium` or `large` (slower).
      2. Follow the instructions to convert models to CoreML. It might take a while!

   2. Install Python bindings for whisper.cpp, with CoreML support (optional) so whisper runs faster.

      ```bash
      pip install --config-settings="--build-option=--accelerate=coreml" whisper-cpp-pybind
      ````

   3. Set environment variables in your `.bashrc` or `.zshrc`:

      ```bash
      export WHISPER_CPP_ROOT=
      ```

      So that `WHISPER_CPP_ROOT` should point to your whisper.cpp installation. It will get the models from there.

4. If you prefer to use OpenAI:

   1. Set environment variables in your `.bashrc` or `.zshrc`:

      ```bash
      export OPENAI_API_KEY=
      ```

5. Be happy.

## Usage

Just `./whisper-dictate.py`, or `./whisper-dictate.py --openai`.

Use `./whisper-dictate.py --help` for more settings.

If using whisper.cpp, the very first time will take a while to load (whisper.cpp model run through CoreML).

Then hold left Opt+Cmd wherever you are on your system, talk, and lift the keys.

The transcript will be typed and copied to the clipboard.