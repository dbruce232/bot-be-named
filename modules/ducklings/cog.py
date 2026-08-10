import os
import asyncio
import gspread
import nextcord
from nextcord.ext import commands
from typing import Union

from utils import (
    discord_utils,
    google_utils,
    logging_utils,
    sheet_utils,
    sheets_constants,
)

"""
Duck module. Module with GSheet-Discord interfacing. See module's README.md for more.
"""


class DucklingCog(commands.Cog, name="Duck"):
    """
    Useful GSheet-Discord commands.
    """

    def __init__(self, bot):
        self.bot = bot
        self.lock = asyncio.Lock()
        self.gdrive_credentials = google_utils.get_gdrive_credentials()
        self.gspread_client = google_utils.create_gspread_client()
        self.drive_service = google_utils.create_google_drive_client()

    async def initoverview(self, ctx, hunturl, sheet):
        """Initializes the overview sheet for the hunt."""
        overview = None

        try:
            overview = sheet.worksheet("Overview")
        # Error when the sheet has no Overview tab
        except gspread.exceptions.WorksheetNotFound:
            embed = discord_utils.create_embed()
            embed.add_field(
                name="Failed",
                value=f"The [sheet]({overview.url}) has no tab named 'Overview'. "
                f"Did you forget to add one?",
                inline=False,
            )
            await discord_utils.send_message(ctx, embed)
            return None

        overview_hunturl_loc = sheets_constants.OVERVIEW_HUNTURL_LOCATION
        overview.update_acell(label=overview_hunturl_loc, value=hunturl)
        return True

    async def createchannel(
        self, ctx, name: str, category_arg: Union[nextcord.CategoryChannel, str] = ""
    ):
        """Command to create channel in a given category. If given no category name, it defaults to current category.

        Permission Category : Verified Roles only.
        Usage: `~createchannel new-channel-name` (creates new-channel-name in the category it's called from)
        Usage: `~createchannel new-channel-name "Category Name"`
        """
        # log command in console
        await logging_utils.log_command(
            "createchannel", ctx.guild, ctx.channel, ctx.author
        )
        embed = discord_utils.create_embed()

        if category_arg == "":
            category = ctx.channel.category
        else:
            category = category_arg

        category = await discord_utils.find_category(ctx, category)

        if category is None:
            if category_arg != "":
                embed.add_field(
                    name="ERROR: Cannot find category",
                    value=f"Sorry, I cannot find a category with name {category_arg}. "
                    f"Please make sure the spelling and capitalization are correct!",
                    inline=False,
                )
                await discord_utils.send_message(ctx, embed)
                return
            else:
                embed.add_field(
                    name="ERROR: Cannot find category",
                    value=f"Sorry, I cannot find the category for the channel {ctx.channel.mention}. "
                    f"Are you sure you are in a category?",
                    inline=False,
                )
                await discord_utils.send_message(ctx, embed)
                return
                # Category channel limit
        if discord_utils.category_is_full(category):
            embed.add_field(
                name="Failed",
                value=f"Category `{category.name}` is already full, max limit is 50 channels.",
            )
            await discord_utils.send_message(ctx, embed)
            return None
        # Server channel limit
        if discord_utils.server_is_full(category.guild):
            embed.add_field(
                name="Failed",
                value=f"Guild `{category.guild.name}` is completely full! Max limit is 500 channels/categories/... Please contact a mod for help.",
            )
            # reply to user
            await discord_utils.send_message(ctx, embed)
            return None

        channel = await discord_utils.createchannelgeneric(ctx.guild, category, name)
        # Send status (success or fail)
        if channel:
            embed.add_field(
                name="Success",
                value=f"Created channel {channel.mention} in `{channel.category.name}`!",
            )
        else:
            embed.add_field(
                name="Failed",
                value="Forbidden! Have you checked if the bot has the required permisisons?",
            )
        await discord_utils.send_message(ctx, embed)

    async def categorycreate(self, ctx, cat_name: str = ""):
        """Create a new category. 
        Usage: ~categorycreate "Name"
        """
        await logging_utils.log_command(
            "category", ctx.guild, ctx.channel, ctx.author
        )
        embed = discord_utils.create_embed()

        if cat_name is None or cat_name == "":
            embed.add_field(
                name="Failed",
                value=f"Error! No category name. Please give me a category to create if you want me to create it.",
            )
            # reply to user
            await discord_utils.send_message(ctx, embed)
            return
        
        try:
            # create category
            await ctx.guild.create_category(cat_name)
            await self.createchannel(ctx, "general", cat_name)
            await self.createchannel(ctx, "bot-spam", cat_name)
        except nextcord.Forbidden:
            embed.add_field(
                name="Failed",
                value="Forbidden! Have you checked if the bot has the `manage_channels` permisisons?",
                inline=False,
            )
            # reply to user
            await discord_utils.send_message(ctx, embed)
            return
        embed.add_field(
            name="Success",
            value=f"Created `{cat_name}`!",
            inline=False,
        )
        await discord_utils.send_message(ctx, embed)

    async def validate_template(self, ctx: commands.Context, proposed_sheet):
            embed = discord_utils.create_embed()
    
            proposed_template = sheet_utils.get_sheet_from_key_or_link(
                self.gspread_client, proposed_sheet
            )
    
            if not proposed_template:
                embed.add_field(
                    name="Failed",
                    value="Sorry, we can't find a sheet there. "
                    "Did you forget to set your sheet as 'Anyone with the link can edit'?",
                    inline=False,
                )
                await discord_utils.send_message(ctx, embed)
                return None
    
            curr_link = proposed_template.url
    
            # Make sure the template tab exists on the sheet.
            try:
                curr_sheet = self.gspread_client.open_by_url(curr_link)
                _template_id = curr_sheet.worksheet("Template").id
            # Error when we can't open the curr sheet link
            except gspread.exceptions.APIError as e:
                error_json = e.response.json()
                error_status = error_json.get("error", {}).get("status")
                if error_status == "PERMISSION_DENIED":
                    embed = discord_utils.create_embed()
                    embed.add_field(
                        name="Failed",
                        value=f"I'm unable to open the tethered [sheet]({curr_link}). "
                        f"Did the permissions change?",
                        inline=False,
                    )
                    await discord_utils.send_message(ctx, embed)
                    return None
                else:
                    raise e
            # Error when the sheet has no template tab
            except gspread.exceptions.WorksheetNotFound:
                embed = discord_utils.create_embed()
                embed.add_field(
                    name="Failed",
                    value=f"The [sheet]({curr_link}) has no tab named 'Template'. "
                    f"Did you forget to add one?",
                    inline=False,
                )
                await discord_utils.send_message(ctx, embed)
                return None
    
            # Make sure the Meta Template tab exists on the sheet.
            try:
                curr_sheet = self.gspread_client.open_by_url(curr_link)
                _overview_id = curr_sheet.worksheet("Meta Template").id
            # Error when the sheet has no Meta Template tab
            except gspread.exceptions.WorksheetNotFound:
                embed = discord_utils.create_embed()
                embed.add_field(
                    name="Failed",
                    value=f"The [sheet]({curr_link}) has no tab named 'Meta Template'. "
                    f"Did you forget to add one?",
                    inline=False,
                )
                await discord_utils.send_message(ctx, embed)
                return None
    
            # Make sure the Overview tab exists on the sheet.
            try:
                curr_sheet = self.gspread_client.open_by_url(curr_link)
                _overview_id = curr_sheet.worksheet("Overview").id
            # Error when the sheet has no Overview tab
            except gspread.exceptions.WorksheetNotFound:
                embed = discord_utils.create_embed()
                embed.add_field(
                    name="Failed",
                    value=f"The [sheet]({curr_link}) has no tab named 'Overview'. "
                    f"Did you forget to add one?",
                    inline=False,
                )
                await discord_utils.send_message(ctx, embed)
                return None
    
            return proposed_template


    async def clonetemplatelion(
        self, ctx: commands.Context, newname
    ):
        """Clones the template and names the new sheet

        For developers: also returns the cloned sheet

        Permission Category : Verified Roles only.
        Usage: ~clonetemplatelion SheetName
        """
        await logging_utils.log_command(
            "clonetemplatelion", ctx.guild, ctx.channel, ctx.author
        )
        embed = discord_utils.create_embed()

        result = os.environ.get("TEMPLATE_SHEET_URL")
        f_id = os.environ.get("TEMPLATE_FOLDER_ID")

        if result is None or f_id is None:
            embed.add_field(
                name="Failed",
                value=f"This server **{ctx.guild.name}** does not have a template Google Sheet.",
                inline=False,
            )
            await discord_utils.send_message(ctx, embed)
            return None


        curr_sheet = self.gspread_client.open_by_url(result)

        new_sheet = ""

        try:
            new_sheet = self.gspread_client.copy(
                file_id=curr_sheet.id,
                title=newname,
                copy_permissions=True,
                folder_id=f_id,
            )
        except Exception as e:
            embed.add_field(
                name="Failed",
                value=f"Invalid folder. {e} Please check to see that you have the correct link and permissions.",
                inline=False,
            )
            await discord_utils.send_message(ctx, embed)
            return None


        embed.add_field(
            name="Success",
            value=f"Cloned sheet located at [sheet link]({new_sheet.url})",
            inline=False,
        )

        await discord_utils.send_message(ctx, embed)
        return new_sheet

    @commands.command(name="newhunt")
    async def newhunt(self, ctx: commands.Context, *args):
        """Creates a new Google sheet and two new categories for a new hunt and then tethers the sheet to the correct category

        
        Usage: ~newhunt "Hunt Name" "http://www.linktopuzzle.com"
        Usage: ~newhunt Hunt Name http://www.linktopuzzle.com
        Usage: ~newhunt Hunt Name
        """
        await logging_utils.log_command("newhunt", ctx.guild, ctx.channel, ctx.author)

        if args[-1].startswith('http'):
            hunt_name = " ".join(args[:-1])
            hunturl = args[-1]
        else:
            hunt_name = " ".join(args)
            hunturl = ""

        try:
            await self.categorycreate(ctx=ctx, cat_name=hunt_name)
            await ctx.guild.create_category(f"{hunt_name} Archive")

            cat = await discord_utils.find_category(ctx, hunt_name)
            if cat is None:
                embed = discord_utils.create_embed()
                embed.add_field(
                    name="Failed",
                    value="Error! The hunt category was not correctly created.",
                )
                # reply to user
                await discord_utils.send_message(ctx, embed)
                return
        except nextcord.Forbidden:
            embed = discord_utils.create_embed()
            embed.add_field(
                name="Failed",
                value="Forbidden! Have you checked if the bot has the required permisisons?",
                inline=False,
            )
            await discord_utils.send_message(ctx, embed)
            return

        new_sheet = await self.clonetemplatelion(ctx, hunt_name)
        if new_sheet is None:
            return

        if await self.validate_template(ctx, new_sheet.url) is None:
            return

        proposed_sheet = sheet_utils.addsheettethergeneric(
            self.gspread_client, new_sheet.url, ctx.guild, cat
        )

        if proposed_sheet:
            new_embed = discord_utils.create_embed()
            new_embed.add_field(
                name="Success",
                value=f"The category **{cat.name}** is now tethered to the "
                f"[Google sheet at link]({proposed_sheet.url})",
                inline=False,
            )
            await discord_utils.send_message(ctx, new_embed)
        # If we can't open the sheet, send an error and return
        else:
            embed = discord_utils.create_embed()
            embed.add_field(
                name="Failed",
                value="Sorry, we can't find a sheet there. "
                "Did you forget to set your sheet as 'Anyone with the link can edit'?",
                inline=False,
            )
            await discord_utils.send_message(ctx, embed)
            return

        if await self.initoverview(ctx, hunturl, new_sheet):
            embed = discord_utils.create_embed()
            embed.add_field(
                name="Success",
                value="The sheet is now set up for use",
                inline=False,
            )
            await discord_utils.send_message(ctx, embed)


def setup(bot):
    bot.add_cog(DucklingCog(bot))
