import discord
from discord.ext import commands
from discord import app_commands, Interaction, ui
from dotenv import load_dotenv
import os
import datetime
import asyncio
import pytz
# Adicione isso no topo do código

load_dotenv()  # Carrega as variáveis do .env
ID_CANAL_REGISTRO_PENDENTE = 1387420027510329505
ID_CATEGORIA_METAS = 1387420207009632309

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

class RegistroModal(ui.Modal, title="🆔 Formulário de Registro"):
    nome = ui.TextInput(label="Nome", placeholder="Ex: Gomes")
    id_user = ui.TextInput(label="ID", placeholder="Ex: 123")
    telefone = ui.TextInput(label="Telefone", placeholder="Ex: 222-222")

    async def on_submit(self, interaction: Interaction):
        canal = bot.get_channel(ID_CANAL_REGISTRO_PENDENTE)
        embed = discord.Embed(title="📋 Novo Pedido de Registro", color=0x3498db)
        embed.add_field(name="Nome:", value=self.nome.value, inline=False)
        embed.add_field(name="ID:", value=self.id_user.value, inline=False)
        embed.add_field(name="Telefone:", value=self.telefone.value, inline=False)
        embed.set_footer(text=f"Solicitado por: {interaction.user} | ID: {interaction.user.id}")

        view = AprovacaoView(self.nome.value, self.id_user.value, interaction.user.id)
        await canal.send(embed=embed, view=view)
        await interaction.response.send_message("✅ Registro enviado para aprovação!", ephemeral=True)

class RegistroView(ui.View):
    @ui.button(label="✅ Fazer Registro", style=discord.ButtonStyle.primary)
    async def abrir_modal(self, interaction: Interaction, button: ui.Button):
        await interaction.response.send_modal(RegistroModal())

class CargoSelect(ui.Select):
    def __init__(self, nome, id_user, membro_id, mensagem_registro, guild):
        options = [
            discord.SelectOption(label=role.name, value=str(role.id))
            for role in guild.roles
            if not role.is_bot_managed() and not role.is_default()
        ]
        super().__init__(placeholder="Selecione um cargo...", options=options)
        self.nome = nome
        self.id_user = id_user
        self.membro_id = membro_id
        self.mensagem_registro = mensagem_registro

    async def callback(self, interaction: Interaction):
        cargo_id = int(self.values[0])
        guild = interaction.guild
        membro = guild.get_member(self.membro_id)
        cargo = guild.get_role(cargo_id)

        if membro:
            novo_nome = f"{self.nome} | {self.id_user}"
            try:
                await membro.edit(nick=novo_nome)
                await membro.add_roles(cargo)
            except Exception as e:
                await interaction.response.send_message(f"❌ Erro ao adicionar cargo ou alterar nick: {e}", ephemeral=True)
                return

            categoria = discord.utils.get(guild.categories, id=ID_CATEGORIA_METAS)
            if categoria:
                canal = await guild.create_text_channel(
                    name=f"{self.nome}-{self.id_user}".replace(" ", "-"),
                    category=categoria
                )
                await canal.set_permissions(membro, view_channel=True, send_messages=True)
                await canal.send(f"✅ Canal criado para {membro.mention}! Use `/meta` aqui para registrar suas metas.")

            await self.mensagem_registro.delete()
            await interaction.response.send_message(f"✅ Membro aprovado, cargo atribuído e canal de metas criado para {membro.mention}!", ephemeral=True)

class CargoSelectView(ui.View):
    def __init__(self, nome, id_user, membro_id, mensagem_registro, guild):
        super().__init__(timeout=60)
        self.add_item(CargoSelect(nome, id_user, membro_id, mensagem_registro, guild))

class AprovacaoView(ui.View):
    def __init__(self, nome, id_user, membro_id):
        super().__init__()
        self.nome = nome
        self.id_user = id_user
        self.membro_id = membro_id

    @ui.button(label="✅ Aprovar", style=discord.ButtonStyle.success)
    async def aprovar(self, interaction: Interaction, button: ui.Button):
        await interaction.response.send_message(
            "Selecione o cargo que deseja atribuir ao membro:",
            view=CargoSelectView(self.nome, self.id_user, self.membro_id, interaction.message, interaction.guild),
            ephemeral=True
        )

    @ui.button(label="❌ Recusar", style=discord.ButtonStyle.danger)
    async def recusar(self, interaction: Interaction, button: ui.Button):
        await interaction.message.delete()
        await interaction.response.send_message("❌ Registro recusado.", ephemeral=True)

class PagarView(ui.View):
    def __init__(self, mensagem):
        super().__init__()
        self.mensagem = mensagem

    @ui.button(label="💸 Pagar", style=discord.ButtonStyle.success)
    async def pagar(self, interaction: Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.manage_roles:
            await interaction.response.send_message("❌ Apenas superiores podem confirmar o pagamento.", ephemeral=True)
            return

        timestamp = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        admin_name = str(interaction.user)

        embed = self.mensagem.embeds[0]
        embed.add_field(
            name="✅ Pagamento Confirmado",
            value=f"Por: {admin_name}\n📅 Data/Hora: {timestamp}",
            inline=False
        )

        await self.mensagem.edit(embed=embed, view=None)
        await interaction.response.send_message(f"✅ Pagamento confirmado por {admin_name} em {timestamp}!", ephemeral=True)

class PagamentoModal(ui.Modal, title="📄 Anexar Comprovante de Pagamento"):
    descricao = ui.TextInput(label="Descrição do Comprovante", placeholder="Ex: Pago via Pix", style=discord.TextStyle.paragraph)

    def __init__(self, mensagem_meta, admin_user):
        super().__init__()
        self.mensagem_meta = mensagem_meta
        self.admin_user = admin_user

    async def on_submit(self, interaction: Interaction):
        timestamp = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        await interaction.response.send_message(
            f"✅ Descrição recebida. Agora, envie o comprovante como anexo nesta conversa.\n📅 {timestamp}\n👤 Aprovado por: {self.admin_user}",
            ephemeral=True
        )

        def check(m):
            return m.author == interaction.user and m.attachments and m.channel == interaction.channel

        try:
            msg = await bot.wait_for('message', check=check, timeout=120)
            comprovante_url = msg.attachments[0].url

            embed = self.mensagem_meta.embeds[0]
            embed.add_field(name="✅ Pagamento Confirmado", value=f"Por: {interaction.user} ({self.admin_user})\nDescrição: {self.descricao.value}\nData/Hora: {timestamp}", inline=False)
            embed.set_image(url=comprovante_url)

            await self.mensagem_meta.edit(embed=embed, view=None)
            await interaction.followup.send("✅ Comprovante anexado e pagamento confirmado!", ephemeral=True)
        except asyncio.TimeoutError:
            await interaction.followup.send("❌ Tempo limite. Nenhum anexo foi enviado.", ephemeral=True)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Bot online como {bot.user}")

@bot.tree.command(name="registro", description="Abrir painel para registro de novos membros")
async def registro(interaction: Interaction):
    await interaction.response.send_message(
        embed=discord.Embed(title="🆔 Registra-se", description="Clique no botão abaixo para iniciar seu registro.", color=0x3498db),
        view=RegistroView(),
        ephemeral=True
    )

@bot.tree.command(name="meta", description="Registrar uma nova meta com data, quantidade e printscreen")
@app_commands.describe(data="Data da meta", quantidade="Quantidade (ex: 10 caixas)", anexo="Printscreen da meta")
async def meta(interaction: Interaction, data: str, quantidade: str, anexo: discord.Attachment):
    canal = interaction.channel
    if canal.category_id != ID_CATEGORIA_METAS:
        await interaction.response.send_message("❌ Este comando só pode ser usado no seu canal de metas.", ephemeral=True)
        return

    embed = discord.Embed(title="✅ Nova Meta Registrada", color=0x2ecc71)
    embed.add_field(name="Data", value=data, inline=False)
    embed.add_field(name="Quantidade", value=quantidade, inline=False)
    embed.set_image(url=anexo.url)
    embed.set_footer(text=f"Registrado por: {interaction.user}")

    view = PagarView(None)
    msg = await canal.send(embed=embed, view=view)
    view.mensagem = msg

    await interaction.response.send_message("✅ Meta registrada com sucesso!", ephemeral=True)

@bot.tree.command(name="lembrete", description="Envia aviso de lembrete nos canais de metas")
async def lembrete(interaction: Interaction):
    guild = interaction.guild
    categoria = discord.utils.get(guild.categories, id=ID_CATEGORIA_METAS)
    if not categoria:
        await interaction.response.send_message("❌ Categoria de metas não encontrada.", ephemeral=True)
        return

    for canal in categoria.text_channels:
        try:
            await canal.send(
                "**Aviso importante 🛈**\n"
                "Todos os membros devem regularizar o pagamento da meta diária facção até o prazo estabelecido.\n"
                "*Pendências serão tratadas com as devidas penalidades.*"
            )
        except Exception as e:
            print(f"Erro ao enviar lembrete em {canal.name}: {e}")

    await interaction.response.send_message("✅ Aviso enviado em todos os canais de metas.", ephemeral=True)

TOKEN = os.getenv("TOKEN")
bot.run(TOKEN)
