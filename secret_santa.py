import datetime
import getopt
import os
import random

# sudo pip install pyyaml
import re
import smtplib
import socket
import sys
import time

import pytz
import yaml

help_message = """
To use, fill out config.yml with your own participants. You can also specify 
DONT_PAIR so that people don't get assigned their significant other.

You'll also need to specify your mail server settings. An example is provided
for routing mail through gmail.

For more information, see README.
"""

CONFIG_REQRD = (
    "SMTP_SERVER",
    "SMTP_PORT",
    "SMTP_USERNAME",
    "SMTP_PASSWORD",
    "TIMEZONE",
    "PARTICIPANTS",
    "DONT_PAIR",
    "FROM",
    "SUBJECT",
    "MESSAGE",
)

CONFIG_OPTIONAL = {
    "SMTP_SECURITY" : "SSL",
    "RNG_SEED" : random.randrange(sys.maxsize)
}

HEADER = """Date: {date}
Content-Type: text/plain; charset="utf-8"
From: {frm}
To: {to}
Subject: {subject}
"""

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yml")

class Person:
    def __init__(self, name, email, invalid_matches):
        self.name = name
        self.email = email
        self.invalid_matches = invalid_matches

    def __str__(self):
        return "%s <%s>" % (self.name, self.email)


class Pair:
    def __init__(self, giver, receiver):
        self.giver = giver
        self.receiver = receiver

    def __str__(self):
        return "%s ---> %s" % (self.giver.name, self.receiver.name)


def parse_yaml(yaml_path=CONFIG_PATH):
    return yaml.load(open(yaml_path), Loader=yaml.FullLoader)


def choose_receiver(giver, receivers):
    choice = random.choice(receivers)
    if choice.name in giver.invalid_matches or giver.name == choice.name:
        if len(receivers) is 1:
            raise Exception("Only one receiver left, try again")
        return choose_receiver(giver, receivers)
    else:
        return choice


def create_pairs(g, r):
    givers = g[:]
    receivers = r[:]
    pairs = []
    for giver in givers:
        try:
            receiver = choose_receiver(giver, receivers)
            receivers.remove(receiver)
            pairs.append(Pair(giver, receiver))
        except:
            return create_pairs(g, r)
    return pairs


class Usage(Exception):
    def __init__(self, msg):
        self.msg = msg


def main(argv=None):
    if argv is None:
        argv = sys.argv
    try:
        try:
            opts, args = getopt.getopt(argv[1:], "shrc", ["send", "help", "reveal"])
        except getopt.error as msg:
            raise Usage(msg)

        # option processing
        send = False
        revealPairs = False
        for option, value in opts:
            if option in ("-s", "--send"):
                send = True
            if option in ("-h", "--help"):
                raise Usage(help_message)
            if option in ("-r", "--reveal"):
                revealPairs = True
                
        config = parse_yaml()
        for key in CONFIG_REQRD:
            if key not in config.keys():
                raise Exception(
                    "Required parameter {} not in yaml config file!".format(key)
                )

        for key, val in CONFIG_OPTIONAL.items():
            if key not in config.keys():
                config.update({key:val})
                print("Optional parameter {} not in yaml config file, using default of {}".format(key,str(val)))
                
        #Setup the RNG with a seed value for repeatable draws (if desired)
        if str(config["RNG_SEED"]).upper() == "YEAR":
            zone = pytz.timezone(config["TIMEZONE"])
            now = zone.localize(datetime.datetime.now())            
            config["RNG_SEED"] = int(now.strftime('%Y'))
        
        random.seed(int(config["RNG_SEED"]))
            
        participants = config["PARTICIPANTS"]
        dont_pair = config["DONT_PAIR"]
        if len(participants) < 2:
            raise Exception("Not enough participants specified.")

        givers = []
        for person in participants:
            name, email = re.match(r"([^<]*)<([^>]*)>", person).groups()
            name = name.strip()
            invalid_matches = []
            for pair in dont_pair:
                names = [n.strip() for n in pair.split(",")]
                if name in names:
                    # is part of this pair
                    for member in names:
                        if name != member:
                            invalid_matches.append(member)
            person = Person(name, email, invalid_matches)
            givers.append(person)

        receivers = givers[:]
        pairs = create_pairs(givers, receivers)
        if not send:
            print(
                """
Test pairings:
                
{}
                
To send out emails with new pairings,
call with the --send argument:

    $ python secret_santa.py --send
            
            """.format("\n".join([str(p) for p in pairs]))
            )

        if send:
            if str(config["SMTP_SECURITY"]).upper() == "TLS":
                server = smtplib.SMTP(config["SMTP_SERVER"], config["SMTP_PORT"])
                server.ehlo()
                server.starttls()
            else:
                server = smtplib.SMTP_SSL(config["SMTP_SERVER"], config["SMTP_PORT"])
                
            server.login(config["SMTP_USERNAME"], config["SMTP_PASSWORD"])
        for pair in pairs:
            zone = pytz.timezone(config["TIMEZONE"])
            now = zone.localize(datetime.datetime.now())
            date = now.strftime("%a, %d %b %Y %T %Z")  # Sun, 21 Dec 2008 06:25:23 +0000
            frm = config["FROM"]
            to = pair.giver.email
            subject = config["SUBJECT"].format(
                santa=pair.giver.name, santee=pair.receiver.name
            )
            msgbody=re.sub(r'(?<!\r)\n',
                       r'\r\n',
                       config["MESSAGE"],
                       flags=re.MULTILINE)
            
            body = (HEADER + "\n\n" + msgbody).format(
                date=date,
                frm=frm,
                to=to,
                subject=subject,
                santa=pair.giver.name,
                santee=pair.receiver.name,
                year=now.strftime('%Y')
            )
            if send:
                server.sendmail(frm, [to], body.encode('utf8'))
                print("Emailed {} <{}>".format(pair.giver.name, to))
        if send:
            server.quit()

        print("""\nNOTE: The RNG seed value was: {}
Write this number down somewhere, if you ever want to regenerate this exact draw (for re-sending pairings, etc).
""".format(config["RNG_SEED"]))
            
        if send and revealPairs:
            print("You chosen to reveal the pairings, are you sure?")
            selection = input("Enter 'Y' to reveal, anything else to skip: ")
            if str(selection[0]).upper() == "Y":
                print("\n".join([str(p) for p in pairs]))
            else:
                print("Reveal aborted, game integrity preserved.")

    except Usage as err:
        print(sys.argv[0].split("/")[-1] + ": " + str(err.msg))
        print("\t for help use --help")
        return 2


if __name__ == "__main__":
    sys.exit(main())
