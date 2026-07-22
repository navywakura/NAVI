# N.A.V.I Command Index

All commands below are available as slash commands. Except for Discord's nested `/social block ...` hierarchy, they are implemented as hybrid commands and also work with the configured prefix. The nested social hierarchy has an equivalent prefix command tree.

## Core

- `/help [category]`
- `/ping`
- `/dashboard`

## Economy and levels

- `/balance [user]`
- `/daily`
- `/work`
- `/pay user amount`
- `/leaderboard`

## Animals

- `/animal cat`
- `/animal dog`
- `/animal fox`
- `/animal bunny`
- `/animal otter`
- `/animal panda`
- `/animal penguin`
- `/animal raccoon`
- `/animal duck`
- `/animal turtle`

## Fun and media

- `/fun petpet user`
- `/fun bonk user`
- `/fun spongify text`
- `/fun stonks user`
- `/fun sus user`
- `/fun match user1 user2 user3 user4`
- `/fun fortune`
- `/fun catfact`
- `/fun dogfact`
- `/fun emojimix emoji1 emoji2`
- `/fun quote message`
- `/fun mockpost text`
- `/8ball question`
- `/choose options`
- `/coinflip`

For `/choose`, separate choices with `|`.

## Games

- `/game guess`
- `/game hangman`
- `/game roll`
- `/game rps`
- `/game tictactoe`
- `/game unscramble`
- `/game trivia`
- `/game connect4`
- `/game memory`

## Social

- `/ship user1 user2`
- `/confess message`
- `/letter user message`
- `/social block add user`
- `/social block remove user`
- `/social block list`
- `/social settings`

Prefix equivalents:

```text
!social block add @user
!social block remove @user
!social block list
!social settings
```

## Marriage

- `/marriage propose user`
- `/marriage accept`
- `/marriage decline`
- `/marriage proposals`
- `/marriage status [user]`
- `/marriage divorce`
- `/marriage leaderboard`

## Roleplay — actions

- `/act dance`
- `/act laugh`
- `/act cry`
- `/act facepalm`
- `/act sleep`
- `/act think`
- `/act sing`
- `/act cook`
- `/act eat`
- `/act run`
- `/act jump`
- `/act wink`
- `/act smug`
- `/act pout`
- `/act clap`

## Roleplay — reactions

- `/react happy`
- `/react sad`
- `/react angry`
- `/react blush`
- `/react bored`
- `/react confused`
- `/react scared`
- `/react smile`
- `/react shrug`
- `/react thinking`
- `/react baka`
- `/react disgust`
- `/react scream`
- `/react peek`
- `/react wasted`

## Roleplay — directed interactions

- `/interact hug user`
- `/interact kiss user`
- `/interact pat user`
- `/interact cuddle user`
- `/interact highfive user`
- `/interact handhold user`
- `/interact feed user`
- `/interact bite user`
- `/interact poke user`
- `/interact bonk user`
- `/interact slap user`
- `/interact heal user`
- `/interact greet user`
- `/interact bye user`
- `/interact cheeks user`

## Reminders and AFK

- `/remind when message`
- `/reminders`
- `/remind-delete reminder_id`
- `/afk [reason]`

Time examples: `10m`, `1h30m`, `2d`.

## Moderation

- `/warn user reason`
- `/warnings [user]`
- `/unwarn warning_id`
- `/timeout user duration reason`
- `/untimeout user reason`
- `/kick user reason`
- `/ban user reason`
- `/unban user_id reason`
- `/purge amount [user]`
- `/slowmode seconds`
- `/lock [channel]`
- `/unlock [channel]`
- `/nickname user [nickname]`

## Information and utilities

- `/avatar [user]`
- `/banner [user]`
- `/userinfo [user]`
- `/serverinfo`
- `/roleinfo role`
- `/channelinfo [channel]`
- `/emojiinfo emoji`
- `/botinfo`
- `/snowflake value`
- `/permissions [user]`

## Image editing

An attachment can be provided, or a member avatar can be used as the source.

- `/image resize width height [attachment] [user]`
- `/image crop x y width height [attachment] [user]`
- `/image rotate [degrees] [attachment] [user]`
- `/image flip [direction] [attachment] [user]`
- `/image grayscale [attachment] [user]`
- `/image invert [attachment] [user]`
- `/image blur [radius] [attachment] [user]`
- `/image sharpen [factor] [attachment] [user]`
- `/image pixelate [block] [attachment] [user]`
- `/image caption text [attachment] [user]`
- `/image quote text [user] [attachment]`
- `/image meme top [bottom] [attachment] [user]`
- `/image avatar [user]`

## Local server tags

- `/tag create name content`
- `/tag show name [arguments]`
- `/tag edit name content`
- `/tag delete name`
- `/tag raw name`
- `/tag list [owner]`
- `/tag search query`
- `/tag info name`
- `/tag claim name`

Supported tag variables:

```text
{user}
{username}
{mention}
{server}
{channel}
{member_count}
{args}
{1} ... {9}
```
