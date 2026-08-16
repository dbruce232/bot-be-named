import os
import asyncio
import gspread
import zipfile
import constants
from pathlib import Path
from modules.archive import archive_utils, archive_constants
from modules.archive.cog import ArchiveCog
import nextcord
from nextcord.ext import commands
from typing import Union, cast

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

    def get_archive_channel(self, ctx: commands.Context):
        for (category, channels) in ctx.guild.by_category():
            for channel in channels:
                if category is None and channel.name == "archive":
                    return channel
        return None

    async def get_start_embed(self, channel_or_guild, multiple_channels=None):
        owner = await self.bot.fetch_user(os.getenv("BOT_OWNER_DISCORD_ID"))
        embed = discord_utils.create_embed()
        embed.add_field(
            name="Archive Started",
            value=f"Your archiving of {channel_or_guild.mention if hasattr(channel_or_guild, 'mention') else channel_or_guild}"
            f" has begun! This may take a while. If I run into "
            f"any errors, I'll let you know.",
            inline=False,
        )
        if multiple_channels:
            embed.add_field(
                name="List of Channels to Archive",
                value=f"{chr(10).join([channel.name for channel in multiple_channels])}",
                inline=False,
            )
        embed.add_field(
            name="Problems?",
            value=f"Taking too long? Let {owner.mention} know",
            inline=False,
        )
        return embed

    async def archive_one_channel(
        self,
        channel: Union[nextcord.TextChannel, nextcord.ForumChannel, nextcord.Thread],
    ) -> Tuple[nextcord.File, int, nextcord.File, int]:
        """Download a channel's history"""
        # Write the chat log. Replace attachments with their filename (for easy reference)
        text_log_path = os.path.join(
            archive_constants.ARCHIVE,
            channel.name + "_" + archive_constants.TEXT_LOG_PATH,
        )
        total_thread_txt_size = 0
        with open(text_log_path, "w") as f:
            if hasattr(channel, "history"):
                channel = cast(nextcord.TextChannel | nextcord.Thread, channel)
                async for msg in channel.history(limit=None, oldest_first=True):
                    await ArchiveCog.archive_message(f, msg)
                    # Threads are attached to normal messages
                    if msg.flags.has_thread and msg.thread:
                        total_thread_txt_size += await self.archive_thread(
                            f, msg.thread
                        )

            elif channel.type == nextcord.ChannelType.forum:
                channel = cast(nextcord.ForumChannel, channel)
                for thread in channel.threads:
                    total_thread_txt_size += await self.archive_thread(f, thread)
                async for thread in channel.archived_threads(limit=None):
                    total_thread_txt_size += await self.archive_thread(f, thread)

            text_file_size = f.tell()

        ZIP_FILENAME = os.path.join(
            archive_constants.ARCHIVE, channel.name + "_archive.zip"
        )
        # Create a zipfile and then walk through all the saved chatlogs and images, and zip em up
        with zipfile.ZipFile(ZIP_FILENAME, mode="w") as zf:
            for root, directories, files in os.walk(archive_constants.ARCHIVE):
                for filename in files:
                    if filename == ZIP_FILENAME.split("/")[-1]:  # Don't include self
                        continue
                    zf.write(
                        os.path.join(root, filename), compress_type=zipfile.ZIP_DEFLATED
                    )
            zf_file_size = zf.fp.tell()
        return (
            nextcord.File(ZIP_FILENAME),
            zf_file_size,
            nextcord.File(text_log_path),
            text_file_size + total_thread_txt_size,
        )

    def get_file_and_embed(
        self, channel, filesize_limit, zip_file, zip_file_size, textfile, textfile_size
    ):
        """Check if zipfile and textfile can be sent or not, create embed with message"""
        embed = discord_utils.create_embed()

        if zip_file_size > filesize_limit:
            # Note that this is an underestimate, since it's not compressed! But it takes a fair amount of text to hit
            # limits.
            if textfile_size > filesize_limit:
                embed.add_field(
                    name="ERROR: History Too Big",
                    value=f"Sorry about that! The chat log in {channel.mention} is too big for me to send.\n"
                    f"The max file size I can send in this server is "
                    f"`{(filesize_limit / constants.BYTES_TO_MEGABYTES):.2f}MB`, but the chat log is "
                    f"`{(textfile_size / constants.BYTES_TO_MEGABYTES):.2f}MB`",
                    inline=False,
                )
                file = None
            else:
                embed.add_field(
                    name="WARNING: Attachments Too Big",
                    value=f"There are too many photos in {channel.mention} for me to send. The max file size "
                    f"I can send in this server is "
                    f"`{(filesize_limit / constants.BYTES_TO_MEGABYTES):.2f}MB` but the zip is "
                    f"`{(zip_file_size / constants.BYTES_TO_MEGABYTES):.2f}MB`. I'll only be able to send you the chat log.",
                    inline=False,
                )
                ZIP_FILENAME = os.path.join(
                    archive_constants.ARCHIVE, channel.name + "_archive.zip"
                )
                with zipfile.ZipFile(ZIP_FILENAME, mode="w") as zf:
                    zf.write(
                        os.path.join(
                            archive_constants.ARCHIVE,
                            channel.name + "_" + archive_constants.TEXT_LOG_PATH,
                        ),
                        compress_type=zipfile.ZIP_DEFLATED,
                    )

                    thread_dir = Path(
                        archive_constants.ARCHIVE,
                        f"{channel.name}_{archive_constants.THREADS}",
                    )

                    # Glob only succeeds if thread_dir exists
                    for thread_file in thread_dir.glob("*.txt"):
                        zf.write(thread_file, compress_type=zipfile.ZIP_DEFLATED)
                file = zip_file
        else:
            file = zip_file
            embed = None
        return file, embed

    async def archivecategory(self, ctx, category_name: str, archive_channel: nextcord.TextChannel):
        """Command to download the history of every text channel in the category

        Permission Category : Verified Roles only.
        Usage: `~archivecategory "Category name"`
        """
        await logging_utils.log_command(
            "archivecategory", ctx.guild, ctx.channel, ctx.author
        )
        embed = discord_utils.create_embed()

        # Check if the user supplied a category
        if len(category_name) < 1:
            # No arguments provided
            embed = discord_utils.create_no_argument_embed("category")
            await archive_channel.send(embed=embed)
            return

        # If we don't have the lock, let the user know it may take a while.
        msg = None
        if self.lock.locked():
            embed = archive_utils.get_delay_embed()
            await archive_channel.send(embed=embed)
        # LOCK EVERYTHING
        async with self.lock:
            if msg:
                await msg.delete()
                msg = None
            category = await discord_utils.find_category(ctx, category_name)
            if category is None:
                embed.add_field(
                    name="ERROR: Cannot find category",
                    value=f"Sorry, I cannot find a category with name {category_name}. "
                    f"Please make sure the spelling and capitalization are correct!",
                    inline=False,
                )
                await archive_channel.send(embed=embed)
                return

            start_embed = await self.get_start_embed(category, category.text_channels)
            msgs = await archive_channel.send(embed=start_embed)

            for text_channel in category.text_channels:
                archive_utils.reset_archive_dir()
                try:
                    (
                        zip_file,
                        zip_file_size,
                        textfile,
                        textfile_size,
                    ) = await self.archive_one_channel(text_channel)
                    file, embed = self.get_file_and_embed(
                        text_channel,
                        ctx.guild.filesize_limit * 0 + constants.HARDCODED_FILE_SIZE,
                        zip_file,
                        zip_file_size,
                        textfile,
                        textfile_size,
                    )
                    await archive_channel.send(file=file, embed=embed)
                except nextcord.errors.Forbidden:
                    embed.add_field(
                        name="ERROR: No access",
                        value=f"Sorry! I don't have access to {text_channel.mention}. You'll need "
                        f"to give me permission to view the channel if you want "
                        f"to archive it",
                        inline=False,
                    )
                    await archive_channel.send(embed=embed)
                    continue
                # There has been an issue with AIO HTTP message sending fails, in which case discord.py crashes?
                # So adding this try/catch for runtime to catch this. I don't think it's a deterministic error
                except RuntimeError:
                    embed = discord_utils.create_embed()
                    embed.add_field(
                        name="ERROR: Failed to send archive",
                        value=f"Sorry! I had trouble sending you the archived file for "
                        f"{text_channel.mention}. Perhaps you can try again with {ctx.prefix}archivechannel"
                        f" after I've finished archiving {category.mention}.",
                        inline=False,
                    )
                    await archive_channel.send(embed=embed)
                    continue
            if msgs:
                await msgs.delete()
            embed = discord_utils.create_embed()
            embed.add_field(
                name="All Done!",
                value=f"Successfully archived {category_name}",
                inline=False,
            )
            await archive_channel.send(embed=embed)
        # Clean up the archive dir
        archive_utils.reset_archive_dir()

    async def deletecategory(self, ctx, archive_channel: nextcord.TextChannel, cat_name: str = ""):
        """Delete a category in the server. Requires emoji confirmation

        Permission Category : Server Moderators only.
        Usage: `~deletecat "Cat A"` (List all the channels in the given category)
        """
        await logging_utils.log_command(
            "deletecategory", ctx.guild, ctx.channel, ctx.author
        )
        embed = discord_utils.create_embed()

        if cat_name == "":
            embed.add_field(
                name="Failed",
                value="No category given",
                inline=False,
            )
            # reply to user
            await archive_channel.send(embed=embed)
            return

        # Return the channel names in a given category
        category = await discord_utils.find_category(ctx, cat_name)

        if category is None:
            embed.add_field(
                name="Failed",
                value=f"Error! The category named `{cat_name}` not found.  Perhaps check your spelling and try again.",
                inline=False,
            )
            # reply to user
            await archive_channel.send(embed=embed)
            return

        channel_list = category.channels

        channels = [f"#{chan.name}" for chan in channel_list]
        if channels == []:
            channels = ["(This Category is empty)"]

        try:
            for channel in channel_list:
                await channel.delete()
            await category.delete()
            embed.add_field(
                name="Success",
                value=f"The category named `{category.name}` has been deleted!",
                inline=False,
            )
            embed.add_field(
                name="Channels deleted",
                value=f"{chr(10).join(channels)}",
                inline=False,
            )
        except:
            embed.add_field(
                name="Failed",
                value=f"The category named `{category.name}` could not be deleted!",
                inline=False,
            )

        finally:
            await archive_channel.send(embed=embed)

    async def confirm_ending(self, ctx: commands.Context, hunt_name: str):
        embed = discord_utils.create_embed()

        proceeding = False

        confirm_emoji = "✅"
        cancel_emoji = "❌"

        # Send warning to user
        embed.add_field(
            name="Are you sure?",
            value=f"This will end {hunt_name} by archiving and then deleting the categories `{hunt_name}` and `{hunt_name} Archive` and all of their channels. This is not reversible. You have 15 seconds to confirm.",
        )

        embs = await discord_utils.send_message(ctx, embed)
        emb = embs[0]
        await emb.add_reaction(confirm_emoji)
        await emb.add_reaction(cancel_emoji)

        # check that the reaction is the correct one and that the correct user reacted
        def check_correct_react(reaction, user):
            return (
                reaction.message.id == emb.id
                and (reaction.emoji == confirm_emoji or reaction.emoji == cancel_emoji)
                and user == ctx.author
            )

        final_embed = discord_utils.create_embed()

        try:
            react, _ = await self.bot.wait_for(
                event="reaction_add", check=check_correct_react, timeout=15
            )
            # delete category
            if react.emoji == confirm_emoji:
                proceeding = True
                final_embed.add_field(
                    name="Success",
                    value=f"Proceeding...",
                    inline=False,
                )
            else:
                final_embed.add_field(
                    name="Canceled",
                    value="The operation was cancelled.",
                    inline=False,
                )

        # CHANGE THIS BEHAVIOR IF BY DEFAULT WE WANT TO DELETE
        except asyncio.TimeoutError:
            final_embed.add_field(name="Canceled", value="The operation was cancelled.")
        finally:
            await discord_utils.send_message(ctx, final_embed)
        return proceeding

    @commands.command(name="endhunt")
    async def endhunt(self, ctx: commands.Context, *args):
        """Archives a hunt and its archive category and deletes them after successful archiving

        
        Usage: ~endhunt "Hunt Name"
        Usage: ~endhunt Hunt Name
        Usage: ~endhunt (if run in the hunt's category or archive category)
        """
        await logging_utils.log_command("endhunt", ctx.guild, ctx.channel, ctx.author)

        embed = discord_utils.create_embed()

        category = ctx.channel.category

        if category is None and len(args) == 0:
            embed.add_field(
                name="Failed",
                value=f"Please provide a hunt to archive",
            )
            # reply to user
            await discord_utils.send_message(ctx, embed)
            return

        if category is None:
            hunt_name = " ".join(args)
        elif category.name.endswith(" Archive"):
            hunt_name = category.name[:-8]
        else:
            hunt_name = category.name

        if await discord_utils.find_category(ctx=ctx, category_name=hunt_name) is None:
            embed.add_field(
                name="Failed",
                value=f"Category {hunt_name} was not found! Please make sure the spelling and capitalization are correct!",
            )
            # reply to user
            await discord_utils.send_message(ctx, embed)
            return

        archive_channel = self.get_archive_channel(ctx)

        if archive_channel is None:
            embed.add_field(
                name="Failed",
                value=f"An Archive channel was not found! Please make sure to create an archive channel to archive to it",
            )
            # reply to user
            await discord_utils.send_message(ctx, embed)
            return

        proceeding = await self.confirm_ending(ctx=ctx, hunt_name=hunt_name)

        if not proceeding:
            return

        await self.archivecategory(ctx=ctx, category_name=hunt_name, archive_channel=archive_channel)
        await self.archivecategory(ctx=ctx, category_name=f"{hunt_name} Archive", archive_channel=archive_channel)

        await self.deletecategory(ctx=ctx, archive_channel=archive_channel, cat_name=hunt_name)
        await self.deletecategory(ctx=ctx, archive_channel=archive_channel, cat_name=f"{hunt_name} Archive")

        final_embed = discord_utils.create_embed()

        final_embed.add_field(
            name="Success",
            value=f"{hunt_name} has ended!",
            inline=False,
        )

        await archive_channel.send(embed=final_embed)

        return


def setup(bot):
    bot.add_cog(DucklingCog(bot))
