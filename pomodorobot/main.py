import sys

from discord.ext.commands import errors as cmd_err

from pomodorobot import lib
from .bot import PomodoroBot
from .config import Config
from .timer import PomodoroTimer, State


USAGE = sys.argv[0] + " <token>"
DESCRIPTION = '''A marinara timer bot that can be configured to your needs.'''

cfg_values = Config("../bot.cfg")

bot = PomodoroBot(
    command_prefix='!',
    description=DESCRIPTION,
    timer_step=2,
    response_lifespan=15,
    pm_help=True
)


@bot.event
async def on_ready():
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('------')

    start_msg = cfg_values.get_str('startup_msg')
    if start_msg is not None and start_msg != "":
        await bot.update_status()
        for server in bot.servers:
            await bot.send_message(server, start_msg)


@bot.command(pass_context=True)
async def setup(ctx, timer_format="default", repeat="True", count_back="True"):
    """ Sets up a timer for the channel in which this command was executed.

    :param ctx: The context in which the command was executed.
    :param timer_format: The string containing the format of the timer.
    :param repeat: Whether the timer should loop back
    to the first period after finishing.
    :param count_back: Whether the timer should show the remaining or elapsed
    time.
    """

    if timer_format == "help":
        help_str = ("**Example:**\n\t" + bot.command_prefix + "setup " +
                    cfg_values.get_str('default_timer_setup'))
        await bot.say(help_str + "\n\t_This will give you a sequence of " +
                      cfg_values.get_str('default_timer_result') + "_")
        return

    if timer_format == "default":
        timer_format = cfg_values.get_str('default_timer_setup')

    channel_id = lib.get_channel_id(ctx)

    result = -1
    if channel_id not in bot.timers.keys():
        try:
            loop = lib.to_boolean(repeat)
            countdown = lib.to_boolean(count_back)

            bot.timers[channel_id] = PomodoroTimer()
            bot.time_messages[channel_id] = None
            bot.list_messages[channel_id] = None

            result, times = bot.timers[channel_id].setup(timer_format,
                                                         loop, countdown)

            if result == 0 and times is not None:
                settings = ("Correctly set up timer config: " + times + "." +
                            "\nLooping is **" + ("ON" if repeat else "OFF") +
                            "**\nCountdown is **" +
                            ("ON" if countdown else "OFF") + "**")

                lib.log(settings, channel_id=channel_id)
                await bot.say(settings,
                              delete_after=bot.response_lifespan * 2)
        except cmd_err.BadArgument:
            result = -4

    if result == -1:  # channel_id is in p_timers.keys() or len(times) > 0
        setup_log = ("Rejecting setup command, " +
                     "there is a period set already established.")
        setup_say = ("I'm already set and ready to go, please use the reset " +
                     "command if you want to change the timer configuration.")

    elif result == -2:  # state == RUNNING or PAUSED
        setup_log = ("Someone tried to modify the timer " +
                     "while it was already running.")
        setup_say = "Please stop the timer completely before modifying it."

    elif result == -3:  # format error
        setup_log = ("Could not set the periods correctly, " +
                     "command 'setup' failed.")
        setup_say = "I did not understand what you wanted, please try again!"

    elif result == -4:  # repeat or countback (arguments) are not valid booleans
        setup_log = ("Could not parse boolean arguments '" + repeat +
                     "' and '" + count_back + "'")
        setup_say = "Invalid arguments received, please try again."
    else:
        return

    lib.log(setup_log, channel_id=channel_id)
    await bot.say(setup_say, delete_after=bot.response_lifespan)


@bot.command(pass_context=True)
async def starttimer(ctx, period_idx=1):
    """ Starts the timer with the recorded setup.
        If none present, or if it's already running,
        it simply gives an error message."""

    channel_id = lib.get_channel_id(ctx)

    if channel_id in bot.timers.keys() and bot.timers[channel_id].is_set():
        if bot.timers[channel_id].start():
            say = None

            if not 0 < period_idx <= len(bot.timers[channel_id].pTimes):
                period_idx = 1

            await bot.run_timer(channel_id, period_idx - 1)
        else:
            say = (lib.get_author_name(ctx) +
                   " tried to start a timer that was already running.")
            await bot.say("This channel's timer is already running",
                          delete_after=bot.response_lifespan)
    else:
        say = (lib.get_author_name(ctx) +
               " tried to start an nonexistent timer.")
        await bot.say("No timer found for this channel.",
                      delete_after=bot.response_lifespan)

    if say is not None:
        lib.log(say, channel_id=channel_id)


@bot.command(pass_context=True)
async def pause(ctx):
    """ Pauses the timer, if it's running. Keeps all settings and current
        period / time. """

    channel_id = lib.get_channel_id(ctx)

    if channel_id in bot.timers.keys():
        if bot.timers[channel_id].pause():
            say = "Timer will be paused soon."
            await bot.say(say, delete_after=bot.timer_step)

        else:
            say = "Could not pause timer, stopped or already running."
            await bot.say("Bruh, I cannot stop something that isn't moving.",
                          delete_after=bot.response_lifespan)

    else:
        say = lib.get_author_name(ctx) + " tried to pause a nonexistent timer."
        await bot.say("No timer found for this channel.",
                      delete_after=bot.response_lifespan)

    lib.log(say, channel_id=channel_id)


@bot.command(pass_context=True)
async def stop(ctx):
    """ Stops the timer, if it's running.
        Resets the current period and time, but keeps the setup. """

    channel_id = lib.get_channel_id(ctx)

    if channel_id in bot.timers.keys():
        if bot.timers[channel_id].stop():
            say = "Timer will stop soon."
            await bot.say(say, delete_after=bot.timer_step)

        else:
            say = "Timer has stopped."
            await bot.say(say)

            await bot.remove_messages(channel_id)

    else:
        say = lib.get_author_name(ctx) + " tried to stop a nonexistent timer."
        await bot.say("No timer found for this channel.",
                      delete_after=bot.response_lifespan)

    lib.log(say, channel_id=channel_id)


@bot.command(pass_context=True)
async def resume(ctx):
    """ Resumes a paused timer. """

    channel_id = lib.get_channel_id(ctx)

    if channel_id in bot.timers.keys():
        if bot.timers[channel_id].resume():
            say = None
            await bot.run_timer(channel_id)
        else:
            say = "Unable to resume timer, stopped or already running."

            if lib.get_author_id(ctx) in \
                    ["244720666018840576", "231948019325468672"]:
                await bot.say(("No grumbles for you, " +
                               lib.get_author_name(ctx, True) + "!"),
                              delete_after=bot.response_lifespan)
            else:
                await bot.say(("**grumble grumble.** The timer is stopped " +
                               "or already running, I can't resume that!"),
                              delete_after=bot.response_lifespan)

    else:
        say = lib.get_author_name(ctx) + " tried to resume a nonexistent timer."
        await bot.say("No timer found for this channel.",
                      delete_after=bot.response_lifespan)

    if say is not None:
        lib.log(say, channel_id=channel_id)


@bot.command(pass_context=True)
async def goto(ctx, period_idx: int):
    """ Skips to the (n-1)th period. """

    channel_id = lib.get_channel_id(ctx)

    if channel_id in bot.timers.keys():
        label = bot.timers[channel_id].goto(period_idx)

        if label is not None:
            say = ("Moved to period number " + str(period_idx) +
                   " (" + label + ")")

            await bot.edit_message(bot.list_messages[channel_id],
                                   bot.timers[channel_id].list_periods())
            if bot.timers[channel_id].state == State.PAUSED:
                await bot.edit_message(bot.time_messages[channel_id],
                                       bot.timers[channel_id].time())

            await bot.say(say)
        else:
            say = "Invalid period number entered when trying goto command."
            await bot.say("Invalid period number.")

    else:
        say = (lib.get_author_name(ctx) +
               " tried changing periods in a nonexistent timer.")
        await bot.say("No timer found for this channel.",
                      delete_after=bot.response_lifespan)

    lib.log(say, channel_id=channel_id)


@bot.command(pass_context=True)
async def reset(ctx):
    """ Resets the timer setup. """

    channel_id = lib.get_channel_id(ctx)

    if channel_id in bot.timers.keys():
        if bot.timers[channel_id].state == State.STOPPED:
            del bot.timers[channel_id]

            del bot.time_messages[channel_id]
            del bot.list_messages[channel_id]

            say = lib.get_author_name(ctx) + " reset the timer."
            await bot.say("Successfully reset session configuration.",
                          delete_after=bot.response_lifespan)
        else:
            say = (lib.get_author_name(ctx) +
                   " tried resetting a timer that was running or paused.")
            await bot.say("Cannot do that while the timer is not stopped.",
                          delete_after=bot.response_lifespan)

    else:
        say = (lib.get_author_name(ctx) +
               " tried resetting a nonexistent timer setup.")
        await bot.say("No timer found for this channel.",
                      delete_after=bot.response_lifespan)

    lib.log(say, channel_id=channel_id)


@bot.command(pass_context=True)
async def superreset(ctx):
    """ Ignores all conditions and resets the channel's timer.	"""

    channel_id = lib.get_channel_id(ctx)

    if lib.get_author_id(ctx) == cfg_values.get_str('admin_id') or \
            lib.author_has_role(ctx, cfg_values.get_str('bot_friend_role_id')):

        if channel_id in bot.timers.keys():
            if bot.timers[channel_id].state == State.RUNNING:
                bot.timers_running -= 1
                await bot.update_status()

            await bot.remove_messages(channel_id)

            del bot.time_messages[channel_id]
            del bot.list_messages[channel_id]

            del bot.timers[channel_id]

            say = "Successfully forced a reset on this channel's timer."
            await bot.say("Timer has been force-reset",
                          delete_after=bot.response_lifespan)
        else:
            say = (lib.get_author_name(ctx) +
                   " tried to force-reset the timer, but no timer was found.")
            await bot.say("No timer found for this channel.",
                          delete_after=bot.response_lifespan)

    else:
        say = (lib.get_author_name(ctx) +
               " attempted to superreset the bot and failed (No permission).")
        await bot.say("You're not my real dad!",
                      delete_after=bot.response_lifespan)

    lib.log(say, channel_id=channel_id)


@bot.command(pass_context=True)
async def time(ctx):
    """ Gives the user the current period and time of the timer. """

    channel_id = lib.get_channel_id(ctx)

    if channel_id in bot.timers.keys():
        say = bot.timers[channel_id].time(True)

        await bot.say(say, delete_after=bot.response_lifespan * 2)

    else:
        say = (lib.get_author_name(ctx) +
               " tried to get the current time of a nonexistent timer.")
        await bot.say("No timer found for this channel.",
                      delete_after=bot.response_lifespan)

    lib.log(say, channel_id=channel_id)


@bot.command(pass_context=True)
async def status(ctx):
    """ Tells the user whether the timer is stopped, running or paused. """

    channel_id = lib.get_channel_id(ctx)

    if channel_id in bot.timers.keys():
        say = bot.timers[channel_id].status()
        await bot.say(say, delete_after=bot.response_lifespan * 2)

    else:
        say = (lib.get_author_name(ctx) +
               " tried to check the status of a nonexistent timer.")
        await bot.say("No timer found for this channel.",
                      delete_after=bot.response_lifespan)

    lib.log(say, channel_id=channel_id)


@bot.command()
async def tts(toggle: str):
    """ Sets the tts option on or off. """

    try:
        bot.tts = lib.to_boolean(toggle)
        say = ("on." if bot.tts else "off.")

        lib.log("TTS now " + say)
        await bot.say("Text-to-speech now " + say, tts=bot.tts,
                      delete_after=bot.response_lifespan)

    except cmd_err.BadArgument:
        lib.log("TTS command failed, bad argument.")
        await bot.say("I could not understand if you wanted to turn TTS " +
                      "on or off, sorry.")


@bot.command(pass_context=True)
async def halp(ctx):
    """ Tells the user how to use the bot. """

    await bot.send_message(ctx.message.author, content="""
**!setup _<format> [loop tts]_**
\tSets the marinara timer up.
\t\tformat    : The periods format. Each period is a set of <name>:<time>, \
where time is in minutes,
\t\t\tand periods are separated by commas. 
\t\trepeat    : Indicates whether the timer should start over when it's done
\t\t\twith the list of periods or simply stop. ('True' or 'False', \
defaults to True)
\t\ttts       : Indicates whether the timer should say period changes \
out loud.
\t\t\t('True' or 'False', defaults to False)
**!starttimer**
\tStarts the timer (must be set up previously).
**!pause**
\tPauses the timer, keeping the current period and time intact.
**!stop**
\tStops the timer, resetting it to the first period and the time to 0
**!resume**
\tRestarts a paused timer.
**!goto _<period-index>_**
\tSkips to the indicated period (Resets the time to 0 within the period).
**!tts _<on|off>_**
\tTurns text-to-speech on or off.
**!time**
\tIf the timer is running, it will show how much time of the current period \
has passed.
**!status**
\tShows whether the timer is stopped, running or paused.
**!halp**
\tShows this message.""")


@bot.command(pass_context=True)
async def shutdown(ctx):
    """ Exits the program. """

    if lib.get_author_id(ctx) == cfg_values.get_str('admin_id'):
        print("Shutting down...")
        await bot.say("Hope I did well, bye!")

        for channel_id, p_timer in bot.timers.items():
            if p_timer.state != State.STOPPED:
                p_timer.stop()
                if lib.get_channel_id(ctx) != channel_id:
                    await bot.send_msg(
                        channel_id,
                        "I'm sorry, I have to go. See you later!"
                    )

                bot.remove_messages(channel_id)
        await bot.logout()
    else:
        lib.log(lib.get_author_name(ctx) + " attempted to stop the bot " +
                "and failed (No permission to shut down)")


@bot.command(pass_context=True)
async def reloadcfg(ctx):
    """ Reloads the configuration. """

    if lib.get_author_id(ctx) == cfg_values.get_str('admin_id') or \
            lib.author_has_role(ctx, cfg_values.get_str('bot_friend_role_id')):

        cfg_values.reload()
        set_bot_config()

        await bot.say("Successfully reloaded configuration.",
                      delete_after=bot.response_lifespan)
        say = "Reloaded configuration."

    else:
        say = (lib.get_author_name(ctx) +
               " attempted to reload the config and failed (No permission).")
        await bot.say("You're not my real dad!",
                      delete_after=bot.response_lifespan)

    lib.log(say)


@bot.command()
async def why(time_out=15):
    """ No need for explanation. """

    await bot.say("https://i.imgur.com/OpFcp.jpg", delete_after=time_out % 60)


def set_bot_config():
    bot.response_lifespan = cfg_values.get_int('response_lifespan')
    bot.command_prefix = cfg_values.get_str('command_prefix')
    bot.timer_step = cfg_values.get_int('timer_step')


if __name__ == '__main__':

    TOKEN = ""
    if len(sys.argv) < 2:
        print("Not enough arguments received!\nUsage: " + sys.argv[0] +
              " <token>")
        exit(-1)

    elif len(sys.argv) == 2:
        TOKEN = sys.argv[1]

    else:
        exit(-2)

    # Config

    if cfg_values.get_str('command_prefix') is None:
        print("Could not find a valid command prefix in the config, aborting.")
        exit(-3)

    # Logging

    lib.init_logger()

    # Bot init

    set_bot_config()
    bot.run(TOKEN)
