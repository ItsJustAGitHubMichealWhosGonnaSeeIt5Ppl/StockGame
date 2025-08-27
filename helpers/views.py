# Views for the Discord Bot
# https://stackoverflow.com/a/76250596

import discord
import datetime
from typing import Callable, Optional, List, Dict, Any, Optional, Union
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

class Pagination(discord.ui.View):
    def __init__(self, interaction: discord.Interaction, page_len:int, embed: discord.Embed, games: list[tuple[str,str]| str], mode: str = 'field', ephemeral: bool = True):
        # Mode field or codeblock
        self.interaction = interaction
        self.games = games # Formatted pages
        self.embed = embed
        self.page_len = page_len if page_len <= 25 else 25 # Maximum page length must be 25
        self.total_pages =  self.compute_total_pages(total_results=len(self.games), results_per_page=self.page_len)
        self.index = 0 # THIS IS STARTING AT 0 ADD 1 TO SHOW VISUAL
        self.ephemeral = ephemeral
        self.mode = mode
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
        if self.mode == 'field':
            for game in self.games[self.page_len * self.index: self.page_len * (self.index +1)]: # Get only the subset of games we're after
                
                    emb.add_field(name=game[0],value=game[1]) # Fill out the embed!
        else: # Codeblock mode
            codeblock_lines = self.games[self.page_len * self.index: self.page_len * (self.index +1)]
            emb.add_field(name='', value='```{lines}```'.format(lines='\n'.join(codeblock_lines)))
                
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


class LeaderboardImageGenerator:
    """
    A class to generate leaderboard images for Discord bot commands.
    Handles image creation, styling, and returns BytesIO buffers for Discord file uploads.
    """
    
    def __init__(self, 
                 width: int = 750,  # Increased width to accommodate new columns
                 base_height: int = 180,
                 row_height: int = 50,
                 theme: str = 'discord_dark'):
        """
        Initialize the LeaderboardImageGenerator.
        
        Args:
            width (int): Image width in pixels
            base_height (int): Base height before adding rows
            row_height (int): Height per leaderboard row
            theme (str): Color theme ('discord_dark', 'light', etc.)
        """
        self.width = width
        self.base_height = base_height
        self.row_height = row_height
        self.theme = theme
        
        # Set color scheme based on theme
        self._set_color_scheme()
        
        # Font sizes
        self.font_sizes = {
            'title': 24,
            'header': 16,
            'text': 14,
            'small': 12
        }
        
        # Load fonts with fallback
        self._load_fonts()
    
    def _set_color_scheme(self):
        """Set colors based on the selected theme."""
        if self.theme == 'discord_dark':
            self.colors = {
                'bg': (47, 49, 54),
                'header': (114, 137, 218),
                'row_bg_1': (54, 57, 63),
                'row_bg_2': (47, 49, 54),
                'text': (255, 255, 255),
                'gold': (255, 215, 0),
                'silver': (192, 192, 192),
                'bronze': (205, 127, 50),
                'footer': (150, 150, 150),
                'positive': (76, 175, 80),  # Green for positive gains
                'negative': (244, 67, 54)   # Red for negative gains
            }
        elif self.theme == 'light':
            self.colors = {
                'bg': (255, 255, 255),
                'header': (66, 139, 202),
                'row_bg_1': (249, 249, 249),
                'row_bg_2': (255, 255, 255),
                'text': (51, 51, 51),
                'gold': (255, 215, 0),
                'silver': (192, 192, 192),
                'bronze': (205, 127, 50),
                'footer': (128, 128, 128),
                'positive': (76, 175, 80),  # Green for positive gains
                'negative': (244, 67, 54)   # Red for negative gains
            }
        else:
            # Default to discord_dark
            self._set_color_scheme_default()
    
    def _set_color_scheme_default(self):
        """Set default color scheme."""
        self.theme = 'discord_dark'
        self._set_color_scheme()
    
    def _load_fonts(self):
        """Load fonts with fallback to default."""
        self.fonts = {}
        font_names = ['arial.ttf', 'Arial.ttf', 'arial.ttc']  # Multiple potential font files
        
        for size_name, size in self.font_sizes.items():
            font_loaded = False
            for font_name in font_names:
                try:
                    self.fonts[size_name] = ImageFont.truetype(font_name, size)
                    font_loaded = True
                    break
                except (OSError, IOError):
                    continue
            
            if not font_loaded:
                # Fallback to default font
                self.fonts[size_name] = ImageFont.load_default()
    
    def create_leaderboard_image(self, 
                               game_data: Dict[str, Any], 
                               leaderboard_data: List[Dict[str, Any]],
                               show_footer: bool = True,
                               custom_title: Optional[str] = None) -> BytesIO:
        """
        Create a leaderboard image from game and leaderboard data.
        
        Args:
            game_data (Dict): Game information containing name, id, owner, etc.
            leaderboard_data (List[Dict]): List of player data dictionaries
            show_footer (bool): Whether to show the bot footer
            custom_title (str, optional): Override the default title
            
        Returns:
            BytesIO: Buffer containing the PNG image
        """
        # Calculate image height
        height = self.base_height + (len(leaderboard_data) * self.row_height)
        
        # Create image
        img = Image.new('RGB', (self.width, height), self.colors['bg'])
        draw = ImageDraw.Draw(img)
        
        y_offset = 20
        
        # Draw title
        title_text = custom_title or f"{game_data.get('name', 'Game')} (ID: {game_data.get('id', 'N/A')})"
        y_offset = self._draw_centered_text(draw, title_text, y_offset, self.fonts['title'], self.colors['text'])
        y_offset += 20
        
        # Draw leaderboard
        y_offset = self._draw_leaderboard_header(draw, y_offset)
        y_offset = self._draw_leaderboard_rows(draw, leaderboard_data, y_offset)
        
        # Add footer if requested
        if show_footer:
            self._draw_footer(draw, height)
        
        # Save to BytesIO buffer
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        
        return buffer
    
    def _draw_centered_text(self, draw: ImageDraw.Draw, text: str, y: int, font, color) -> int:
        """Draw centered text and return new y position."""
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (self.width - text_width) // 2
        draw.text((x, y), text, fill=color, font=font)
        return y + text_height + 10
    
    def _draw_leaderboard_header(self, draw: ImageDraw.Draw, y_offset: int) -> int:
        """Draw leaderboard header."""
        header_rect = [0, y_offset, self.width, y_offset + 40]
        draw.rectangle(header_rect, fill=self.colors['header'])
        
        # Header text - updated with new columns
        headers = [
            (20, "Rank"),
            (100, "Investor"),
            (300, "Portfolio"),
            (450, "$ Gain"),
            (550, "% Gain"),
            (650, "Joined")
        ]
        
        for x, header_text in headers:
            draw.text((x, y_offset + 10), header_text, fill=self.colors['text'], font=self.fonts['header'])
        
        return y_offset + 40
    
    def _draw_leaderboard_rows(self, draw: ImageDraw.Draw, leaderboard_data: List[Dict], y_offset: int) -> int:
        """Draw leaderboard rows."""
        pos_indicators = [f'{i}.' for i in range(1, len(leaderboard_data) + 1)]
        
        for idx, player_data in enumerate(leaderboard_data):
            # Alternating row colors
            row_color = self.colors['row_bg_1'] if idx % 2 == 0 else self.colors['row_bg_2']
            row_rect = [0, y_offset, self.width, y_offset + self.row_height]
            draw.rectangle(row_rect, fill=row_color)
            
            # Rank indicator with special colors for top 3
            rank_text = pos_indicators[idx] if idx < len(pos_indicators) else f"{idx + 1}."
            rank_color = self._get_rank_color(idx)
            draw.text((20, y_offset + 15), rank_text, fill=rank_color, font=self.fonts['text'])
            
            # Player name
            player_name = player_data.get('display_name', f"ID({player_data.get('user_id', 'Unknown')})")
            if len(player_name) > 20:
                player_name = player_name[:19] + "..."
            draw.text((100, y_offset + 15), player_name, fill=self.colors['text'], font=self.fonts['text'])
            
            # Portfolio value
            current_value = player_data.get('current_value', 0)
            portfolio_value = f"${float(current_value):,.2f}"
            draw.text((300, y_offset + 15), portfolio_value, fill=self.colors['text'], font=self.fonts['text'])
            
            # Dollar gain/loss with color coding
            change_dollars = player_data.get('change_dollars', 0)
            dollar_change = f"${float(change_dollars):+,.2f}"  # + sign for positive, - for negative
            dollar_color = self.colors['positive'] if change_dollars >= 0 else self.colors['negative']
            draw.text((450, y_offset + 15), dollar_change, fill=dollar_color, font=self.fonts['text'])
            
            # Percentage gain/loss with color coding
            change_percent = player_data.get('change_percent', 0)
            percent_change = f"{float(change_percent):+.2f}%"  # + sign for positive, - for negative
            percent_color = self.colors['positive'] if change_percent >= 0 else self.colors['negative']
            draw.text((550, y_offset + 15), percent_change, fill=percent_color, font=self.fonts['text'])
            
            # Join date
            joined = player_data.get('joined', '')
            if isinstance(joined, str):
                join_date = joined[:10] if len(joined) >= 10 else joined
            else:
                # Handle datetime objects
                join_date = joined.strftime("%Y-%m-%d") if joined else "Unknown"
            draw.text((650, y_offset + 15), join_date, fill=self.colors['text'], font=self.fonts['text'])
            
            y_offset += self.row_height
        
        return int(y_offset)  # Ensure return type is int
    
    def _get_rank_color(self, rank: int) -> tuple:
        """Get color for rank position."""
        if rank == 0:
            return self.colors['gold']
        elif rank == 1:
            return self.colors['silver']
        elif rank == 2:
            return self.colors['bronze']
        else:
            return self.colors['text']
    
    def _draw_footer(self, draw: ImageDraw.Draw, height: int, last_updated: Optional[datetime.datetime] = None):
        """Draw footer text."""
        draw.text((20, height - 25), "Last Updated: " +
                  (last_updated.strftime("%Y-%m-%d %H:%M:%S") if last_updated else "Generated by StockBot"),
                 fill=self.colors['footer'], font=self.fonts['small'])

# Usage example functions (can be imported and used in your bot commands)
def create_game_leaderboard_image(game_data: Dict[str, Any], 
                                leaderboard_data: List[Dict[str, Any]],
                                theme: str = 'discord_dark') -> BytesIO:
    """
    Convenience function to create a game leaderboard image.
    
    Args:
        game_data: Game information dictionary
        leaderboard_data: List of player data dictionaries
        theme: Color theme to use
        
    Returns:
        BytesIO buffer containing the PNG image
    """
    generator = LeaderboardImageGenerator(theme=theme)
    return generator.create_leaderboard_image(game_data, leaderboard_data)

class StockPortfolioImageGenerator:
    """
    A class to generate stock portfolio images for Discord bot commands.
    Handles image creation, styling, and returns BytesIO buffers for Discord file uploads.
    """
    
    def __init__(self, 
                 width: int = 700,
                 base_height: int = 130,
                 row_height: int = 45,
                 theme: str = 'discord_dark'):
        """
        Initialize the StockPortfolioImageGenerator.
        
        Args:
            width (int): Image width in pixels
            base_height (int): Base height before adding rows
            row_height (int): Height per stock row
            theme (str): Color theme ('discord_dark', 'light', etc.)
        """
        self.width = width
        self.base_height = base_height
        self.row_height = row_height
        self.theme = theme
        
        # Set color scheme based on theme
        self._set_color_scheme()
        
        # Font sizes
        self.font_sizes = {
            'title': 24,
            'header': 16,
            'text': 14,
            'small': 12
        }
        
        # Load fonts with fallback
        self._load_fonts()
    
    def _set_color_scheme(self):
        """Set colors based on the selected theme."""
        if self.theme == 'discord_dark':
            self.colors = {
                'bg': (47, 49, 54),
                'header': (114, 137, 218),
                'row_bg_1': (54, 57, 63),
                'row_bg_2': (47, 49, 54),
                'text': (255, 255, 255),
                'footer': (150, 150, 150),
                'positive': (76, 175, 80),  # Green for positive gains
                'negative': (244, 67, 54),  # Red for negative gains
                'neutral': (255, 255, 255),  # White for neutral/no data
                'ticker_bg': (32, 34, 37),  # Darker background for ticker
                'border': (72, 75, 81),
                'summary_bg': (88, 101, 242)  # Discord blurple for summary
            }
        elif self.theme == 'light':
            self.colors = {
                'bg': (255, 255, 255),
                'header': (66, 139, 202),
                'row_bg_1': (249, 249, 249),
                'row_bg_2': (255, 255, 255),
                'text': (51, 51, 51),
                'footer': (128, 128, 128),
                'positive': (76, 175, 80),
                'negative': (244, 67, 54),
                'neutral': (51, 51, 51),
                'ticker_bg': (240, 240, 240),
                'border': (200, 200, 200),
                'summary_bg': (66, 139, 202)
            }
        else:
            # Default to discord_dark
            self.theme = 'discord_dark'
            self._set_color_scheme()
    
    def _load_fonts(self):
        """Load fonts with fallback to default."""
        self.fonts = {}
        font_names = ['arial.ttf', 'Arial.ttf', 'arial.ttc']
        
        for size_name, size in self.font_sizes.items():
            font_loaded = False
            for font_name in font_names:
                try:
                    self.fonts[size_name] = ImageFont.truetype(font_name, size)
                    font_loaded = True
                    break
                except (OSError, IOError):
                    continue
            
            if not font_loaded:
                self.fonts[size_name] = ImageFont.load_default()
    
    def create_portfolio_image(self, 
                             user_data: Dict[str, Any], 
                             game_data: Dict[str, Any],
                             stock_picks: List[Dict[str, Any]],
                             show_footer: bool = True) -> BytesIO:
        """
        Create a stock portfolio image from user, game, and stock data.
        
        Args:
            user_data (Dict): User information containing display_name, etc.
            game_data (Dict): Game information containing name, id, etc.
            stock_picks (List[Dict]): List of stock pick dictionaries
            show_footer (bool): Whether to show the bot footer
            
        Returns:
            BytesIO: Buffer containing the PNG image
        """
        # Filter only owned stocks for display
        owned_stocks = [pick for pick in stock_picks if pick.get('status') == 'owned']
        
        # Calculate image height
        extra_height = 120 if owned_stocks else 80  # Extra space for summary or no stocks message
        height = self.base_height + (len(owned_stocks) * self.row_height) + extra_height
        
        # Create image
        img = Image.new('RGB', (self.width, height), self.colors['bg'])
        draw = ImageDraw.Draw(img)
        
        y_offset = 20
        
        # Draw title
        user_name = user_data.get('display_name', 'Unknown User')
        game_name = game_data.get('name', 'Unknown Game')
        game_id = game_data.get('id', 'N/A')
        
        title_text = f"{user_name}'s Portfolio"
        subtitle_text = f"Game: {game_name} (ID: {game_id})"
        
        y_offset = self._draw_centered_text(draw, title_text, y_offset, self.fonts['title'], self.colors['text'])
        y_offset = self._draw_centered_text(draw, subtitle_text, y_offset, self.fonts['text'], self.colors['footer'])
        y_offset += 15
        
        if owned_stocks:
            # Calculate and draw portfolio summary
            y_offset = self._draw_portfolio_summary(draw, owned_stocks, y_offset)
            y_offset += 20
            
            # Draw stock table
            y_offset = self._draw_stock_header(draw, y_offset)
            y_offset = self._draw_stock_rows(draw, owned_stocks, y_offset)
        else:
            # No stocks message
            no_stocks_text = "No stocks currently owned"
            y_offset = self._draw_centered_text(draw, no_stocks_text, y_offset + 40, 
                                              self.fonts['text'], self.colors['footer'])
        
        # Add footer if requested
        if show_footer:
            self._draw_footer(draw, height, last_updated=stock_picks[0].get('last_updated'))

        # Save to BytesIO buffer
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        
        return buffer
    
    def _draw_centered_text(self, draw: ImageDraw.Draw, text: str, y: int, font, color) -> int:
        """Draw centered text and return new y position."""
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (self.width - text_width) // 2
        draw.text((x, y), text, fill=color, font=font)
        return y + text_height + 10
    
    def _draw_portfolio_summary(self, draw: ImageDraw.Draw, owned_stocks: List[Dict], y_offset: int) -> int:
        """Draw portfolio summary section."""
        # Calculate totals
        total_value = sum(float(stock.get('current_value', 0)) for stock in owned_stocks)
        total_gain_dollars = sum(float(stock.get('change_dollars', 0)) for stock in owned_stocks)
        
        # Calculate percentage gain (avoid division by zero)
        total_invested = total_value - total_gain_dollars
        total_gain_percent = (total_gain_dollars / total_invested * 100) if total_invested != 0 else 0
        
        # Summary box
        summary_rect = [50, y_offset, self.width - 50, y_offset + 60]
        draw.rectangle(summary_rect, fill=self.colors['summary_bg'], outline=self.colors['border'])
        
        # Summary text in three columns
        col1_x = 70
        col2_x = 310
        col3_x = 550
        text_y = y_offset + 12
        
        # Portfolio value (white)
        draw.text((col1_x, text_y), "Total Portfolio Value:", fill=self.colors['text'], font=self.fonts['text'])
        draw.text((col1_x, text_y + 20), f"${total_value:,.2f}", fill=self.colors['text'], font=self.fonts['header'])
        
        # Dollar gain (color coded)
        gain_color = self.colors['positive'] if total_gain_dollars >= 0 else self.colors['negative']
        draw.text((col2_x, text_y), "Total Gain/Loss:", fill=self.colors['text'], font=self.fonts['text'])
        draw.text((col2_x, text_y + 20), f"${total_gain_dollars:+,.2f}", fill=gain_color, font=self.fonts['header'])
        
        # Percentage return (color coded)
        percent_color = self.colors['positive'] if total_gain_percent >= 0 else self.colors['negative']
        draw.text((col3_x, text_y), "Total Return:", fill=self.colors['text'], font=self.fonts['text'])
        draw.text((col3_x, text_y + 20), f"{total_gain_percent:+.2f}%", fill=percent_color, font=self.fonts['header'])
        
        return y_offset + 60
    
    def _draw_stock_header(self, draw: ImageDraw.Draw, y_offset: int) -> int:
        """Draw stock table header."""
        header_rect = [20, y_offset, self.width - 20, y_offset + 35]
        draw.rectangle(header_rect, fill=self.colors['header'])
        
        # Header columns with better spacing
        headers = [
            (40, "Ticker"),
            (120, "Price"),
            (220, "Shares"),
            (330, "Value"),
            (460, "$ Gain"),
            (580, "% Gain")
        ]
        
        for x, header_text in headers:
            draw.text((x, y_offset + 10), header_text, fill=self.colors['text'], font=self.fonts['header'])
        
        return y_offset + 35
    
    def _draw_stock_rows(self, draw: ImageDraw.Draw, owned_stocks: List[Dict], y_offset: int) -> int:
        """Draw stock rows."""
        for idx, stock in enumerate(owned_stocks):
            # Alternating row colors
            row_color = self.colors['row_bg_1'] if idx % 2 == 0 else self.colors['row_bg_2']
            row_rect = [20, y_offset, self.width - 20, y_offset + self.row_height]
            draw.rectangle(row_rect, fill=row_color)
            
            # Extract stock data with safe defaults
            ticker = str(stock.get('stock_ticker', 'N/A'))
            shares = float(stock.get('shares', 0))
            current_value = float(stock.get('current_value', 0))
            change_dollars = float(stock.get('change_dollars', 0))
            change_percent = float(stock.get('change_percent', 0))
            
            # Calculate share price
            share_price = current_value / shares if shares > 0 else 0
            
            # Draw ticker (with background highlight)
            ticker_rect = [25, y_offset + 8, 95, y_offset + self.row_height - 8]
            draw.rectangle(ticker_rect, fill=self.colors['ticker_bg'])
            bbox = draw.textbbox((0, 0), ticker, font=self.fonts['text'])
            ticker_text_width = bbox[2] - bbox[0]
            ticker_rect_center_x = (ticker_rect[0] + ticker_rect[2]) // 2
            ticker_text_x = ticker_rect_center_x - (ticker_text_width // 2)
            draw.text((ticker_text_x, y_offset + 15), ticker, fill=self.colors['text'], font=self.fonts['text'])
            
            # Draw price
            price_text = f"${share_price:,.2f}"
            draw.text((120, y_offset + 15), price_text, fill=self.colors['text'], font=self.fonts['text'])
            
            # Draw shares
            shares_text = f"{shares:,.2f}" if shares else "0"
            draw.text((220, y_offset + 15), shares_text, fill=self.colors['text'], font=self.fonts['text'])
            
            # Draw value
            value_text = f"${current_value:,.2f}"
            draw.text((330, y_offset + 15), value_text, fill=self.colors['text'], font=self.fonts['text'])
            
            # Draw dollar gain (color coded)
            dollar_text = f"${change_dollars:+,.2f}"
            dollar_color = self.colors['positive'] if change_dollars >= 0 else self.colors['negative']
            draw.text((460, y_offset + 15), dollar_text, fill=dollar_color, font=self.fonts['text'])
            
            # Draw percentage gain (color coded)
            percent_text = f"{change_percent:+.2f}%"
            percent_color = self.colors['positive'] if change_percent >= 0 else self.colors['negative']
            draw.text((580, y_offset + 15), percent_text, fill=percent_color, font=self.fonts['text'])
            
            y_offset += self.row_height
        
        return y_offset
    
    def _draw_footer(self, draw: ImageDraw.Draw, height: int, last_updated: Optional[datetime.datetime] = None):
        """Draw footer text."""
        draw.text((20, height - 25), "Last Updated: " +
                  (last_updated.strftime("%Y-%m-%d %H:%M:%S") if last_updated else "Generated by StockBot"), 
                 fill=self.colors['footer'], font=self.fonts['small'])


# Convenience function to create portfolio image
def create_portfolio_image(user_data: Dict[str, Any],
                          game_data: Dict[str, Any], 
                          stock_picks: List[Dict[str, Any]],
                          theme: str = 'discord_dark') -> BytesIO:
    """
    Convenience function to create a stock portfolio image.
    
    Args:
        user_data: User information dictionary
        game_data: Game information dictionary  
        stock_picks: List of stock pick dictionaries
        theme: Color theme to use
        
    Returns:
        BytesIO buffer containing the PNG image
    """
    generator = StockPortfolioImageGenerator(theme=theme)
    return generator.create_portfolio_image(user_data, game_data, stock_picks)
