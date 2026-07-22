from pathlib import Path


EXPECTED_SNIPPETS = {
    "core.py": ["name=\"help\"", "name=\"ping\"", "name=\"dashboard\""],
    "animals.py": [f"name=\"{name}\"" for name in ("cat", "dog", "fox", "bunny", "otter", "panda", "penguin", "raccoon", "duck", "turtle")],
    "fun_media.py": [f"name=\"{name}\"" for name in ("petpet", "bonk", "spongify", "stonks", "sus", "match", "fortune", "catfact", "dogfact", "emojimix", "quote", "mockpost")],
    "games.py": [f"name=\"{name}\"" for name in ("guess", "hangman", "roll", "rps", "tictactoe", "unscramble", "trivia", "connect4", "memory")],
    "social.py": [f"name=\"{name}\"" for name in ("ship", "confess", "letter", "social", "block", "add", "remove", "list", "settings", "marriage", "propose", "accept", "decline", "proposals", "status", "divorce", "leaderboard")],
    "roleplay.py": [f"name=\"{name}\"" for name in (
        "dance", "laugh", "cry", "facepalm", "sleep", "think", "sing", "cook", "eat", "run", "jump", "wink", "smug", "pout", "clap",
        "happy", "sad", "angry", "blush", "bored", "confused", "scared", "smile", "shrug", "thinking", "baka", "disgust", "scream", "peek", "wasted",
        "hug", "kiss", "pat", "cuddle", "highfive", "handhold", "feed", "bite", "poke", "bonk", "slap", "heal", "greet", "bye", "cheeks",
    )],
    "reminders.py": [f"name=\"{name}\"" for name in ("remind", "reminders", "remind-delete", "afk")],
    "moderation.py": [f"name=\"{name}\"" for name in ("warn", "warnings", "unwarn", "timeout", "untimeout", "kick", "ban", "unban", "purge", "slowmode", "lock", "unlock", "nickname")],
    "information.py": [f"name=\"{name}\"" for name in ("avatar", "banner", "userinfo", "serverinfo", "roleinfo", "channelinfo", "emojiinfo", "botinfo", "snowflake", "permissions")],
    "images.py": [f"name=\"{name}\"" for name in ("resize", "crop", "rotate", "flip", "grayscale", "invert", "blur", "sharpen", "pixelate", "caption", "quote", "meme", "avatar")],
    "tags.py": [f"name=\"{name}\"" for name in ("create", "show", "edit", "delete", "raw", "list", "search", "info", "claim")],
}


def test_requested_commands_are_declared() -> None:
    cogs = Path(__file__).parents[1] / "bot" / "cogs"
    missing: list[str] = []
    for filename, snippets in EXPECTED_SNIPPETS.items():
        source = (cogs / filename).read_text(encoding="utf-8")
        for snippet in snippets:
            if snippet not in source:
                missing.append(f"{filename}: {snippet}")
    assert not missing, "Missing command declarations: " + ", ".join(missing)


def test_prefix_command_regression_is_covered() -> None:
    root = Path(__file__).parents[1]
    economy = (root / "bot" / "cogs" / "economy.py").read_text(encoding="utf-8")
    client = (root / "bot" / "client.py").read_text(encoding="utf-8")
    assert '@commands.hybrid_command(name="work"' in economy
    assert "commands.CommandNotFound" in client
    assert "dynamic_prefix" in client
