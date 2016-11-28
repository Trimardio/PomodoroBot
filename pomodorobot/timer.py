import re
from enum import Enum

import pomodorobot.lib as lib


class State(Enum):
    """ Represents the states in which a pomdoro timer can be.
    """

    STOPPED = -1
    RUNNING = 1
    PAUSED = 2

    @staticmethod
    def to_string(state):
        if state == State.RUNNING:
            return "RUNNING"
        elif state == State.PAUSED:
            return "PAUSED"
        elif state == State.STOPPED:
            return "STOPPED"
        return None


class Action(Enum):
    """ Represents the actions that a pomodoro timer can do.
    """

    NONE = 0
    RUN = 1
    PAUSE = 2
    STOP = 3


class PomodoroTimer:
    """ A class representing a pomodoro timer.
    """

    # The times for the different periods the timer has been setup with
    times = []
    # The labels or names for each of the set periods
    names = []

    # The period the timer is currently at.
    curr_period = -1
    # The current time within the period.
    curr_time = 0

    # The current timer's status
    state = State.STOPPED
    # The action the timer should react to on the next iteration of the loop
    action = Action.NONE

    # Whether the period list should loop or not.
    _repeat = True
    # Whether the timer should count from 0 and show the "elapsed" time,
    # or count back from the period's time and show the remaining time.
    _countdown = True
    # Whether the bot should speak this timer's alerts out loud or not.
    tts = False

    def __init__(self):
        self.times = []
        self.names = []

    def setup(self, periods_format: str, on_repeat: bool, reverse: bool):
        """ Sets the pomodoro timer up with its periods, periods' names and
            extra options

        :param periods_format: The string containing the periods and
            their names, in a format similar to that of a dictionary.
            Ex.: PeriodA:10,PeriodB:5,PeriodC:15
                 This will create 3 periods of 10, 5 and 15 minutes each.
            It also accepts segments with the format (nxName1:t1,Name2:t2),
            which creates n iterations of Name1:t1,Name2:t2 periods (Where
            Name1 and Name2 are the period names and t1, t2 the respective
            times).
            Ex.: (3xPeriodA:10,PeriodB:5),PeriodC:15
                This will create 7 periods of times 10,5,10,5,10,5 and 15 each.
        :type periods_format:str

        :param on_repeat: Whether the timer should go back to period 0 after
            going through the complete list (True) or not (False).
        :type on_repeat: bool

        :param reverse: Whether the timer should should remaining (True) or
            elapsed (False) time.
        :type reverse bool

        :return: Returns an integer with a success/fail code, and if the timer
            was successfully set, it will also return a string with the periods'
            times, separated by commas.

            The codes are:
                 0 -> Success.
                -1 -> Timer already set up.
                -2 -> Timer already running.
                -3 -> Format error (periods_format was malformed).
        """

        if len(self.times) > 0:
            return -1, None

        if self.state == State.RUNNING or self.state == State.PAUSED:
            return -2, None

        raw_sections = re.sub(r",(?=[^()]*\))", '.', periods_format).split(',')

        loop = True
        if ':' in periods_format:
            if ',' in periods_format:
                fmt_err = False
            else:
                try:
                    attempt = periods_format.split(':')
                    self.names.append(attempt[0])
                    self.times.append(int(attempt[1]))
                    fmt_err = False
                    loop = False
                except ValueError:
                    fmt_err = True
        else:
            fmt_err = True

        if not fmt_err and loop:
            for section in raw_sections:
                if section.startswith('(') and section.endswith(')'):

                    section = section.replace('(', '').replace(')', '')
                    splits = section.split('x')

                    sub_sections = []

                    for s in splits[1].strip().split('.'):
                        sub_sections.append(s.split(':'))
                        if len(sub_sections[len(sub_sections) - 1]) != 2:
                            fmt_err = True
                            break
                    if fmt_err:
                        break

                    for i in range(0, int(splits[0]) * len(sub_sections)):
                        idx = i % len(sub_sections)

                        time = int(sub_sections[idx][1])
                        if time == 0:
                            continue
                        self.names.append(
                            sub_sections[idx][0].replace('_', ' ')
                        )
                        self.times.append(time)
                else:
                    splits_b = section.split(':')
                    if len(splits_b) != 2:
                        fmt_err = True
                        break

                    time = int(splits_b[1])
                    if time == 0:
                        continue
                    self.names.append(splits_b[0].replace('_', ' '))
                    self.times.append(time)

        if not fmt_err:
            concat = str(self.times[0])
            if len(self.times) > 1:
                for i in range(1, len(self.times)):
                    concat += ", " + str(self.times[i])

            self._repeat = on_repeat
            self._countdown = reverse

            return 0, concat
        else:
            return -3, None

    def start(self) -> bool:
        """ Starts the timer.

        :return: True if successful, False if it was already running.
        """

        if self.state == State.RUNNING:
            return False

        self.action = Action.RUN
        return True

    def pause(self) -> bool:
        """ Pauses the timer, if it's running. Keeps all settings and
            current period and elapsed (or remaining) time.

        :return: True if the timer was running and got paused, False otherwise
            (No need to pause then).
        """

        if self.state == State.RUNNING:
            self.action = Action.PAUSE
            return True
        return False

    def resume(self) -> bool:
        """ Resumes the timer, if it was actually paused. Complains if not.

        :return: True the timer was actually paused and got resumed
            successfully, False if it was running or stopped.
        """

        if self.state == State.PAUSED:
            self.start()
            return True
        return False

    def stop(self) -> bool:
        """ Attempts to stop the timer.

        :return: True if the timer was running and got stopped successfully,
            False if the timer was paused or about to be (Timer actually
            gets stopped, cancelling the pause state/action).

        """

        if self.state == State.RUNNING:
            self.action = Action.STOP
            return True

        elif self.state == State.PAUSED or self.action == Action.PAUSED:
            self.action = Action.NONE
            self.state = State.STOPPED

            self.curr_time = 0
            self.curr_period = -1

            return False

    def goto(self, idx: int):
        """ Skips to the n-th period, assuming the periods are counted 1 -> n
            (Thus it actually jumps to [idx-1]).

        :param idx: The index of the period to jump to.
        :return: If successful, returns the name of the new current period.
            If not, returns None.
        """

        if 0 < idx <= len(self.times):
            self.curr_period = idx - 1
            self.curr_time = 0
            return self.names[self.curr_period]
        return None

    def is_set(self) -> bool:
        """ Tells whether the timer is already set up or not.

        :return: True if the timer is set and ready to go, False otherwise.
        """

        return len(self.times) > 0

    def status(self) -> str:
        """ Tells whether the timer is stopped, running or paused, as well as
            the next timer's action.

        :return: A string stating the current status, whether it's correctly set
            up or not, and the next action it's going to take.
        """

        status = "Currently " + State.to_string(self.state).lower()

        if len(self.times) == 0:
            status += " and not properly set up."
        else:
            status += "."

        if not self.action == Action.NONE:
            status += " Will soon "
            if self.action == Action.RUN:
                status += "start running."
            elif self.action == Action.PAUSE:
                status += "pause."
            elif self.action == Action.STOP:
                status += "stop."

        return status

    def time(self, extended=False) -> str:
        """ Generates a string containing the timer's current period and time.

        :param extended: Whether it should display extra information (True)
            or keep it simple (False).
        :return: The string with the current period and the remaining or elapsed
            time (Depending on the value of _countdown, see PomodoroTimer.setup)
        """

        if self.state == State.STOPPED:
            return "Currently not running."

        time = "**On " + self.names[self.curr_period] + " period** "

        if extended:
            time += "(Duration: " + lib.pluralize(
                self.times[self.curr_period], "minute", append='s') + ")"

        if self._countdown:
            time += "\nRemaining:\t"
            m, s = divmod(
                (self.times[self.curr_period] * 60) - self.curr_time, 60
            )
        else:
            time += "\nElapsed:\t"
            m, s = divmod(self.curr_time, 60)

        h, m = divmod(m, 60)

        time += "%02d:%02d:%02d" % (h, m, s)
        del h, m, s

        if self.state == State.PAUSED:
            time += "\t**(PAUSED)**"

        return time

    def list_periods(self):
        """ Generates a list of the periods as a string, flagging the
            current one.
        :return: The list of periods, specifying which one is the current one.
        """

        p_list = "**Period list (Loop is " + (
                 "ON" if self._repeat else "OFF") + "):**"
        for i in range(0, len(self.times)):
            p_list += ("\n" + self.names[i] + ": " +
                       lib.pluralize(self.times[i], "minute", append='s'))

            if i == self.curr_period:
                p_list += "\t-> _You are here!_"

        return p_list
