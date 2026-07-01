# Voice Typing

Talk instead of type. Voice Typing turns your speech into text in any app on Windows: click into a text box, press a hotkey, and start talking. Everything runs locally with Whisper, so it works offline and nothing you say leaves your computer.

## What it does

- Types into anything you'd normally type in: browsers, chat windows, code editors, search bars.
- Runs fully offline. No account to sign up for, nothing uploaded anywhere.
- Handles 20 languages, or it can just auto-detect the one you're speaking.
- Lets you choose between speed and accuracy. The "small" model is fast, "large-v3" is the most accurate, and it'll use an NVIDIA GPU on its own if you have one.
- Has an optional grammar and spelling fix you can switch on. That runs offline too.
- Follows whatever microphone is set as your default, headsets included.

## Getting started

The easy way is to download VoiceTyping.exe from the Releases page and double-click it. The first run downloads the speech model once (a few hundred MB), and after that you're set. The app isn't code-signed, so Windows may pop a SmartScreen warning the first time. Click "More info", then "Run anyway".

If you'd rather run it from the Python source, you'll need Python 3.9 or newer (tick "Add Python to PATH" while installing). Then run setup.bat, which installs the dependencies and drops a shortcut on your desktop. Start it from there, or with run.bat.

## Using it

Click where you want the words to land, press Alt + Up, and talk. Press Alt + Up again to stop. There's also a button in the app window if you'd rather not use the keyboard. Language, microphone, model, and the grammar switch all live in the app and save themselves.

Two things that catch people out. There's a short delay before text appears, because Whisper waits for you to finish a phrase before it transcribes. And the text goes to whichever window has focus, so click your target first. The hotkey is set up so it won't steal focus away from it.

## Building the exe yourself

If you don't want the prebuilt download, run build_exe.bat and you'll get dist/VoiceTyping.exe. There's also a GitHub Action that does it for you: push a version tag like v1.0 and it builds the exe and attaches it to that release.

## Extra scripts

- "Enable GPU (large-v3).bat" installs the NVIDIA CUDA libraries so the most accurate model runs fast. Skip it and the app just uses your CPU instead.
- "Start with Windows.bat" makes it launch automatically when you sign in.

## How it works, roughly

It's Python. faster-whisper does the speech-to-text, the window is built with customtkinter, and the optional grammar check uses LanguageTool.

## License

MIT, © 2026 yukirtxreal-ctrl. Use it however you like.
