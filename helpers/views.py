# Views for the Discord Bot
# https://stackoverflow.com/a/76250596

import typing
import discord
from typing import Callable, Optional



class Pagination(discord.ui.View):
    def __init__(self, interaction: discord.Interaction, page_len:int, embed: discord.Embed, games: list[tuple[str,str]], ephemeral: bool = True):
        self.interaction = interaction
        self.games = games # Formatted pages
        self.embed = embed
        self.page_len = page_len if page_len <= 25 else 25 # Maximum page length must be 25
        self.total_pages =  self.compute_total_pages(total_results=len(self.games), results_per_page=self.page_len)
        self.index = 0 # THIS IS STARTING AT 0 ADD 1 TO SHOW VISUAL
        self.ephemeral = ephemeral
        super().__init__(timeout=100)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user == self.interaction.user:
            return True
        else:
            emb = discord.Embed(
                description=f"Only the author of the command can perform this action.",
                color=16711680
            )
            await interaction.response.send_message(embed=emb, ephemeral=self.ephemeral)
            return False
        
    def get_page(self): # Return an embed object of current page
        self.embed.set_footer(text=f"Page {self.index + 1} of {self.total_pages} | Dates are formatted as (YYYY/MM/DD)") # Set a footer
        emb = self.embed.copy()
    
        for game in self.games[self.page_len * self.index: self.page_len * (self.index +1)]: # Get only the subset of games we're after
            emb.add_field(name=game[0],value=game[1]) # Fill out the embed!
        return emb
    
    async def navigate(self):
        emb = self.get_page() 
        if self.total_pages == 1:
            await self.interaction.response.send_message(embed=emb, ephemeral=self.ephemeral)
        elif self.total_pages > 1:
            self.update_buttons()
            await self.interaction.response.send_message(embed=emb, view=self, ephemeral=self.ephemeral)

    async def edit_page(self, interaction: discord.Interaction):
        emb = self.get_page()
        self.update_buttons()
        await interaction.response.edit_message(embed=emb, view=self)

    def update_buttons(self):
        if self.index > self.total_pages // 2:
            self.children[2].emoji = "⏮️"
        else:
            self.children[2].emoji = "⏭️"
            
        self.children[0].disabled = self.index == 0
        self.children[1].disabled = self.index +1 == self.total_pages

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.blurple)
    async def previous(self, interaction: discord.Interaction, button: discord.Button):
        self.index -= 1
        await self.edit_page(interaction)

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.blurple)
    async def next(self, interaction: discord.Interaction, button: discord.Button):
        self.index += 1
        await self.edit_page(interaction)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.blurple)
    async def end(self, interaction: discord.Interaction, button: discord.Button):
        if self.index <= self.total_pages//2:
            self.index = self.total_pages -1
        else:
            self.index = 0
        await self.edit_page(interaction)

    async def on_timeout(self):
        # remove buttons on timeout
        message = await self.interaction.original_response()
        await message.edit(view=None)

    @staticmethod
    def compute_total_pages(total_results: int, results_per_page: int) -> int:
        # Divide total results (-1) by results per page,  +1
        return ((total_results - 1) // results_per_page) + 1
