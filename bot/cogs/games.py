from __future__ import annotations

import random
from dataclasses import dataclass

import discord
from discord.ext import commands

from bot.client import NaviBot
from bot.utils.context import require_guild_module, send_response
from database.connection import AsyncSessionLocal
from database.models import GameStat

WORDS = (
    "python", "terminal", "servidor", "discord", "network", "kernel", "database",
    "protocol", "cipher", "gateway", "operator", "navi", "matrix", "packet",
)
TRIVIA = (
    ("¿Qué protocolo traduce nombres de dominio?", ("DNS", "SSH", "SMTP", "NTP"), 0),
    ("¿Qué puerto usa HTTPS por defecto?", ("22", "53", "443", "8080"), 2),
    ("¿Cuál es una estructura sin duplicados en Python?", ("list", "set", "tuple", "str"), 1),
    ("¿Qué comando Git crea una copia local de un repositorio?", ("pull", "clone", "fork", "merge"), 1),
)


async def record_game(guild_id: int, user_id: int, game: str, result: str) -> None:
    async with AsyncSessionLocal() as session:
        row = await session.get(GameStat, (guild_id, user_id, game))
        if row is None:
            row = GameStat(guild_id=guild_id, user_id=user_id, game=game)
            session.add(row)
        if result == "win":
            row.wins += 1
        elif result == "loss":
            row.losses += 1
        else:
            row.draws += 1
        await session.commit()


class OwnerView(discord.ui.View):
    def __init__(self, owner_id: int, *, timeout: float = 180) -> None:
        super().__init__(timeout=timeout)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Esta partida pertenece a otro operador.", ephemeral=True)
            return False
        return True


class GuessModal(discord.ui.Modal, title="Adivina el número"):
    value = discord.ui.TextInput(label="Número (1-100)", min_length=1, max_length=3)

    def __init__(self, view: "GuessView") -> None:
        super().__init__()
        self.game_view = view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            guess = int(self.value.value)
        except ValueError:
            await interaction.response.send_message("Introduce un número válido.", ephemeral=True)
            return
        self.game_view.attempts += 1
        if guess == self.game_view.number:
            self.game_view.stop()
            for child in self.game_view.children:
                child.disabled = True
            await record_game(self.game_view.guild_id, interaction.user.id, "guess", "win")
            await interaction.response.edit_message(
                content=f"✅ Número correcto: **{guess}** en {self.game_view.attempts} intentos.",
                view=self.game_view,
            )
        else:
            hint = "mayor" if guess < self.game_view.number else "menor"
            await interaction.response.send_message(f"Incorrecto. El número es **{hint}**.", ephemeral=True)


class GuessView(OwnerView):
    def __init__(self, owner_id: int, guild_id: int) -> None:
        super().__init__(owner_id)
        self.guild_id = guild_id
        self.number = random.randint(1, 100)
        self.attempts = 0

    @discord.ui.button(label="Adivinar", style=discord.ButtonStyle.primary, emoji="🔢")
    async def guess(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        await interaction.response.send_modal(GuessModal(self))

    @discord.ui.button(label="Rendirse", style=discord.ButtonStyle.danger)
    async def surrender(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        for child in self.children:
            child.disabled = True
        self.stop()
        await record_game(self.guild_id, interaction.user.id, "guess", "loss")
        await interaction.response.edit_message(content=f"Partida terminada. El número era **{self.number}**.", view=self)


class TextAttemptModal(discord.ui.Modal):
    answer = discord.ui.TextInput(label="Respuesta", min_length=1, max_length=30)

    def __init__(self, title: str, callback) -> None:
        super().__init__(title=title)
        self.submit_callback = callback

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.submit_callback(interaction, self.answer.value.strip().lower())


class HangmanView(OwnerView):
    def __init__(self, owner_id: int, guild_id: int) -> None:
        super().__init__(owner_id)
        self.guild_id = guild_id
        self.word = random.choice(WORDS)
        self.guessed: set[str] = set()
        self.errors = 0

    def display(self) -> str:
        masked = " ".join(char if char in self.guessed else "_" for char in self.word)
        used = " ".join(sorted(self.guessed)) or "—"
        return f"**{masked}**\nErrores: `{self.errors}/6` · Usadas: `{used}`"

    @discord.ui.button(label="Probar letra/palabra", style=discord.ButtonStyle.primary)
    async def attempt(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        await interaction.response.send_modal(TextAttemptModal("Ahorcado", self.handle_attempt))

    async def handle_attempt(self, interaction: discord.Interaction, answer: str) -> None:
        won = False
        if len(answer) == 1 and answer.isalpha():
            if answer in self.guessed:
                await interaction.response.send_message("Esa letra ya fue usada.", ephemeral=True)
                return
            self.guessed.add(answer)
            if answer not in self.word:
                self.errors += 1
            won = all(char in self.guessed for char in self.word)
        else:
            won = answer == self.word
            if not won:
                self.errors += 1
        if won or self.errors >= 6:
            for child in self.children:
                child.disabled = True
            self.stop()
            result = "win" if won else "loss"
            await record_game(self.guild_id, interaction.user.id, "hangman", result)
            text = f"{'✅ Victoria' if won else '❌ Derrota'}. Palabra: **{self.word}**."
            await interaction.response.edit_message(content=text, view=self)
            return
        await interaction.response.edit_message(content=self.display(), view=self)


class RPSView(OwnerView):
    EMOJI = {"rock": "🪨", "paper": "📄", "scissors": "✂️"}

    def __init__(self, owner_id: int, guild_id: int) -> None:
        super().__init__(owner_id, timeout=60)
        self.guild_id = guild_id

    async def play(self, interaction: discord.Interaction, choice: str) -> None:
        bot_choice = random.choice(tuple(self.EMOJI))
        if choice == bot_choice:
            result = "draw"
        elif (choice, bot_choice) in {("rock", "scissors"), ("paper", "rock"), ("scissors", "paper")}:
            result = "win"
        else:
            result = "loss"
        await record_game(self.guild_id, interaction.user.id, "rps", result)
        for child in self.children:
            child.disabled = True
        labels = {"win": "Victoria", "loss": "Derrota", "draw": "Empate"}
        await interaction.response.edit_message(
            content=f"Tú: {self.EMOJI[choice]} · N.A.V.I: {self.EMOJI[bot_choice]}\n**{labels[result]}**",
            view=self,
        )
        self.stop()

    @discord.ui.button(emoji="🪨", style=discord.ButtonStyle.secondary)
    async def rock(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        await self.play(interaction, "rock")

    @discord.ui.button(emoji="📄", style=discord.ButtonStyle.secondary)
    async def paper(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        await self.play(interaction, "paper")

    @discord.ui.button(emoji="✂️", style=discord.ButtonStyle.secondary)
    async def scissors(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        await self.play(interaction, "scissors")


class TicTacToeButton(discord.ui.Button):
    def __init__(self, index: int) -> None:
        super().__init__(label="\u200b", style=discord.ButtonStyle.secondary, row=index // 3)
        self.index = index

    async def callback(self, interaction: discord.Interaction) -> None:
        view: TicTacToeView = self.view  # type: ignore[assignment]
        await view.handle_move(interaction, self)


class TicTacToeView(discord.ui.View):
    WINS = ((0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6))

    def __init__(self, owner: discord.Member, opponent: discord.Member | None, guild_id: int) -> None:
        super().__init__(timeout=180)
        self.owner = owner
        self.opponent = opponent
        self.guild_id = guild_id
        self.board = [0] * 9
        self.turn = owner.id
        for index in range(9):
            self.add_item(TicTacToeButton(index))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        allowed = {self.owner.id}
        if self.opponent:
            allowed.add(self.opponent.id)
        if interaction.user.id not in allowed:
            await interaction.response.send_message("No participas en esta partida.", ephemeral=True)
            return False
        if interaction.user.id != self.turn:
            await interaction.response.send_message("No es tu turno.", ephemeral=True)
            return False
        return True

    def winner(self) -> int | None:
        for a, b, c in self.WINS:
            if self.board[a] and self.board[a] == self.board[b] == self.board[c]:
                return self.board[a]
        return 0 if all(self.board) else None

    async def handle_move(self, interaction: discord.Interaction, button: TicTacToeButton) -> None:
        if self.board[button.index]:
            await interaction.response.send_message("Casilla ocupada.", ephemeral=True)
            return
        mark = 1 if interaction.user.id == self.owner.id else 2
        self.board[button.index] = mark
        button.label = "X" if mark == 1 else "O"
        button.style = discord.ButtonStyle.primary if mark == 1 else discord.ButtonStyle.success
        button.disabled = True
        winner = self.winner()
        if winner is not None:
            for child in self.children:
                child.disabled = True
            if winner == 0:
                content = "**Empate.**"
                await record_game(self.guild_id, self.owner.id, "tictactoe", "draw")
                if self.opponent:
                    await record_game(self.guild_id, self.opponent.id, "tictactoe", "draw")
            else:
                won_user = self.owner if winner == 1 else self.opponent
                content = f"Ganador: **{won_user.display_name if won_user else 'N.A.V.I'}**"
                if won_user:
                    await record_game(self.guild_id, won_user.id, "tictactoe", "win")
                loser = self.opponent if winner == 1 else self.owner
                if loser:
                    await record_game(self.guild_id, loser.id, "tictactoe", "loss")
            await interaction.response.edit_message(content=content, view=self)
            self.stop()
            return
        if self.opponent:
            self.turn = self.opponent.id if interaction.user.id == self.owner.id else self.owner.id
            await interaction.response.edit_message(content=f"Turno: <@{self.turn}>", view=self)
        else:
            available = [i for i, value in enumerate(self.board) if not value]
            bot_index = random.choice(available)
            self.board[bot_index] = 2
            bot_button = self.children[bot_index]
            bot_button.label = "O"
            bot_button.style = discord.ButtonStyle.success
            bot_button.disabled = True
            winner = self.winner()
            if winner is not None:
                for child in self.children:
                    child.disabled = True
                if winner == 0:
                    text, result = "**Empate.**", "draw"
                elif winner == 2:
                    text, result = "N.A.V.I gana la partida.", "loss"
                else:
                    text, result = f"Ganador: **{self.owner.display_name}**", "win"
                await record_game(self.guild_id, self.owner.id, "tictactoe", result)
                await interaction.response.edit_message(content=text, view=self)
                self.stop()
                return
            self.turn = self.owner.id
            await interaction.response.edit_message(content=f"Turno: {self.owner.mention}", view=self)


class UnscrambleView(OwnerView):
    def __init__(self, owner_id: int, guild_id: int) -> None:
        super().__init__(owner_id)
        self.guild_id = guild_id
        self.word = random.choice(WORDS)
        chars = list(self.word)
        while "".join(chars) == self.word:
            random.shuffle(chars)
        self.scrambled = "".join(chars)

    @discord.ui.button(label="Responder", style=discord.ButtonStyle.primary)
    async def answer(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        await interaction.response.send_modal(TextAttemptModal("Palabra desordenada", self.handle_answer))

    async def handle_answer(self, interaction: discord.Interaction, answer: str) -> None:
        if answer == self.word:
            for child in self.children:
                child.disabled = True
            await record_game(self.guild_id, interaction.user.id, "unscramble", "win")
            await interaction.response.edit_message(content=f"✅ Correcto: **{self.word}**", view=self)
            self.stop()
        else:
            await interaction.response.send_message("Respuesta incorrecta.", ephemeral=True)


class TriviaView(OwnerView):
    def __init__(self, owner_id: int, guild_id: int, question: str, options: tuple[str, ...], correct: int) -> None:
        super().__init__(owner_id, timeout=60)
        self.guild_id = guild_id
        self.question = question
        self.options = options
        self.correct = correct
        for index, option in enumerate(options):
            button = discord.ui.Button(label=option, style=discord.ButtonStyle.secondary, row=index // 2)
            button.callback = self._callback(index)
            self.add_item(button)

    def _callback(self, index: int):
        async def callback(interaction: discord.Interaction) -> None:
            correct = index == self.correct
            for child in self.children:
                child.disabled = True
            self.children[index].style = discord.ButtonStyle.success if correct else discord.ButtonStyle.danger
            if not correct:
                self.children[self.correct].style = discord.ButtonStyle.success
            await record_game(self.guild_id, interaction.user.id, "trivia", "win" if correct else "loss")
            await interaction.response.edit_message(
                content=f"{self.question}\n{'✅ Correcto' if correct else f'❌ Correcta: **{self.options[self.correct]}**'}",
                view=self,
            )
            self.stop()
        return callback


class ConnectButton(discord.ui.Button):
    def __init__(self, column: int) -> None:
        super().__init__(label=str(column + 1), style=discord.ButtonStyle.secondary, row=column // 5)
        self.column = column

    async def callback(self, interaction: discord.Interaction) -> None:
        view: Connect4View = self.view  # type: ignore[assignment]
        await view.drop(interaction, self.column)


class Connect4View(discord.ui.View):
    def __init__(self, owner: discord.Member, opponent: discord.Member | None, guild_id: int) -> None:
        super().__init__(timeout=240)
        self.owner = owner
        self.opponent = opponent
        self.guild_id = guild_id
        self.turn = owner.id
        self.grid = [[0 for _ in range(7)] for _ in range(6)]
        for column in range(7):
            self.add_item(ConnectButton(column))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        allowed = {self.owner.id}
        if self.opponent:
            allowed.add(self.opponent.id)
        if interaction.user.id not in allowed or interaction.user.id != self.turn:
            await interaction.response.send_message("No es tu turno.", ephemeral=True)
            return False
        return True

    def render(self) -> str:
        tokens = {0: "⚫", 1: "🔴", 2: "🟡"}
        return "\n".join("".join(tokens[value] for value in row) for row in self.grid) + "\n1️⃣2️⃣3️⃣4️⃣5️⃣6️⃣7️⃣"

    def winner(self) -> int | None:
        for row in range(6):
            for col in range(7):
                token = self.grid[row][col]
                if not token:
                    continue
                for dr, dc in ((0,1),(1,0),(1,1),(1,-1)):
                    if all(0 <= row+dr*i < 6 and 0 <= col+dc*i < 7 and self.grid[row+dr*i][col+dc*i] == token for i in range(4)):
                        return token
        return 0 if all(self.grid[0]) else None

    async def drop(self, interaction: discord.Interaction, column: int) -> None:
        row = next((r for r in range(5, -1, -1) if self.grid[r][column] == 0), None)
        if row is None:
            await interaction.response.send_message("Columna completa.", ephemeral=True)
            return
        token = 1 if interaction.user.id == self.owner.id else 2
        self.grid[row][column] = token
        winner = self.winner()
        if winner is not None:
            for child in self.children:
                child.disabled = True
            if winner == 0:
                text = self.render() + "\n**Empate.**"
                await record_game(self.guild_id, self.owner.id, "connect4", "draw")
                if self.opponent:
                    await record_game(self.guild_id, self.opponent.id, "connect4", "draw")
            else:
                won = self.owner if winner == 1 else self.opponent
                text = self.render() + f"\nGanador: **{won.display_name if won else 'N.A.V.I'}**"
                await record_game(self.guild_id, self.owner.id, "connect4", "win" if winner == 1 else "loss")
                if self.opponent:
                    await record_game(self.guild_id, self.opponent.id, "connect4", "win" if winner == 2 else "loss")
            await interaction.response.edit_message(content=text, view=self)
            self.stop()
            return
        if self.opponent:
            self.turn = self.opponent.id if interaction.user.id == self.owner.id else self.owner.id
        else:
            choices = [c for c in range(7) if self.grid[0][c] == 0]
            bot_column = random.choice(choices)
            bot_row = next(r for r in range(5, -1, -1) if self.grid[r][bot_column] == 0)
            self.grid[bot_row][bot_column] = 2
            winner = self.winner()
            if winner is not None:
                for child in self.children:
                    child.disabled = True
                result = "loss" if winner == 2 else "draw"
                await record_game(self.guild_id, self.owner.id, "connect4", result)
                await interaction.response.edit_message(content=self.render() + ("\nN.A.V.I gana." if winner == 2 else "\nEmpate."), view=self)
                self.stop()
                return
            self.turn = self.owner.id
        await interaction.response.edit_message(content=self.render() + f"\nTurno: <@{self.turn}>", view=self)


class MemoryButton(discord.ui.Button):
    def __init__(self, index: int) -> None:
        super().__init__(label="?", style=discord.ButtonStyle.secondary, row=index // 4)
        self.index = index

    async def callback(self, interaction: discord.Interaction) -> None:
        view: MemoryView = self.view  # type: ignore[assignment]
        await view.reveal(interaction, self)


class MemoryView(OwnerView):
    EMOJIS = ["🔐", "💾", "🛰️", "🧠", "⚙️", "📡", "🧬", "🖥️"]

    def __init__(self, owner_id: int, guild_id: int) -> None:
        super().__init__(owner_id, timeout=240)
        self.guild_id = guild_id
        self.values = self.EMOJIS * 2
        random.shuffle(self.values)
        self.opened: list[int] = []
        self.matched: set[int] = set()
        self.moves = 0
        for index in range(16):
            self.add_item(MemoryButton(index))

    async def reveal(self, interaction: discord.Interaction, button: MemoryButton) -> None:
        if button.index in self.matched or button.index in self.opened:
            await interaction.response.send_message("Celda ya revelada.", ephemeral=True)
            return
        button.label = self.values[button.index]
        button.style = discord.ButtonStyle.primary
        self.opened.append(button.index)
        if len(self.opened) == 1:
            await interaction.response.edit_message(content=f"Movimientos: {self.moves}", view=self)
            return
        self.moves += 1
        first, second = self.opened
        if self.values[first] == self.values[second]:
            self.matched.update(self.opened)
            for index in self.opened:
                self.children[index].style = discord.ButtonStyle.success
                self.children[index].disabled = True
            self.opened.clear()
            if len(self.matched) == 16:
                await record_game(self.guild_id, interaction.user.id, "memory", "win")
                await interaction.response.edit_message(content=f"✅ Memoria completada en **{self.moves}** movimientos.", view=self)
                self.stop()
                return
            await interaction.response.edit_message(content=f"Movimientos: {self.moves}", view=self)
            return
        hide = discord.ui.Button(label="Ocultar", style=discord.ButtonStyle.danger, row=4)
        async def hide_callback(hide_interaction: discord.Interaction) -> None:
            for index in self.opened:
                self.children[index].label = "?"
                self.children[index].style = discord.ButtonStyle.secondary
            self.opened.clear()
            self.remove_item(hide)
            await hide_interaction.response.edit_message(content=f"Movimientos: {self.moves}", view=self)
        hide.callback = hide_callback
        self.add_item(hide)
        await interaction.response.edit_message(content=f"Movimientos: {self.moves} · No coinciden. Pulsa `Ocultar`.", view=self)


class GamesCog(commands.Cog):
    def __init__(self, bot: NaviBot) -> None:
        self.bot = bot

    @commands.hybrid_group(name="game", description="Minijuegos interactivos.", invoke_without_command=True)
    async def game(self, ctx: commands.Context) -> None:
        await send_response(ctx, "Juegos: guess, hangman, roll, rps, tictactoe, unscramble, trivia, connect4, memory.", ephemeral=True)

    async def _guard(self, ctx: commands.Context) -> bool:
        return await require_guild_module(ctx, self.bot, "games")

    @game.command(name="guess", description="Adivina un número entre 1 y 100.")
    async def guess(self, ctx: commands.Context) -> None:
        if await self._guard(ctx):
            await send_response(ctx, "He seleccionado un número entre **1 y 100**.", view=GuessView(ctx.author.id, ctx.guild.id))

    @game.command(name="hangman", description="Juega al ahorcado.")
    async def hangman(self, ctx: commands.Context) -> None:
        if await self._guard(ctx):
            view = HangmanView(ctx.author.id, ctx.guild.id)
            await send_response(ctx, view.display(), view=view)

    @game.command(name="roll", description="Lanza dados. Ejemplo: /game roll dice:2 sides:20")
    async def roll(self, ctx: commands.Context, dice: int = 1, sides: int = 6) -> None:
        if not await self._guard(ctx):
            return
        dice = max(1, min(20, dice))
        sides = max(2, min(1000, sides))
        values = [random.randint(1, sides) for _ in range(dice)]
        await send_response(ctx, f"🎲 `{dice}d{sides}` → {', '.join(map(str, values))} · **Total {sum(values)}**")

    @game.command(name="rps", description="Piedra, papel o tijeras contra N.A.V.I.")
    async def rps(self, ctx: commands.Context) -> None:
        if await self._guard(ctx):
            await send_response(ctx, "Selecciona tu vector:", view=RPSView(ctx.author.id, ctx.guild.id))

    @game.command(name="tictactoe", description="Tres en raya contra otro usuario o N.A.V.I.")
    async def tictactoe(self, ctx: commands.Context, opponent: discord.Member | None = None) -> None:
        if not await self._guard(ctx):
            return
        if opponent and (opponent.bot or opponent.id == ctx.author.id):
            await send_response(ctx, "Oponente inválido.", ephemeral=True)
            return
        view = TicTacToeView(ctx.author, opponent, ctx.guild.id)
        await send_response(ctx, f"Turno: {ctx.author.mention}", view=view)

    @game.command(name="unscramble", description="Ordena una palabra mezclada.")
    async def unscramble(self, ctx: commands.Context) -> None:
        if await self._guard(ctx):
            view = UnscrambleView(ctx.author.id, ctx.guild.id)
            await send_response(ctx, f"Ordena: **{view.scrambled.upper()}**", view=view)

    @game.command(name="trivia", description="Responde una pregunta de cultura técnica.")
    async def trivia(self, ctx: commands.Context) -> None:
        if await self._guard(ctx):
            question, options, correct = random.choice(TRIVIA)
            await send_response(ctx, question, view=TriviaView(ctx.author.id, ctx.guild.id, question, options, correct))

    @game.command(name="connect4", description="Conecta cuatro fichas contra otro usuario o N.A.V.I.")
    async def connect4(self, ctx: commands.Context, opponent: discord.Member | None = None) -> None:
        if not await self._guard(ctx):
            return
        if opponent and (opponent.bot or opponent.id == ctx.author.id):
            await send_response(ctx, "Oponente inválido.", ephemeral=True)
            return
        view = Connect4View(ctx.author, opponent, ctx.guild.id)
        await send_response(ctx, view.render() + f"\nTurno: {ctx.author.mention}", view=view)

    @game.command(name="memory", description="Completa una cuadrícula de memoria.")
    async def memory(self, ctx: commands.Context) -> None:
        if await self._guard(ctx):
            await send_response(ctx, "Memoriza y encuentra las parejas.", view=MemoryView(ctx.author.id, ctx.guild.id))


async def setup(bot: NaviBot) -> None:
    await bot.add_cog(GamesCog(bot))
