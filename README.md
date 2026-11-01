# codetime

A small command-line app that tracks how long you code and emails you a report.

Start the timer when you sit down to code, stop it when you finish, and get a summary by project and by day. It uses only Python's standard library, so there is nothing to install.

## Features

- Start and stop a timer from the terminal
- Sessions are named after the current folder, or any name you choose
- Reports for today, this week, this month, or all time
- Totals by project and by day, with sessions that cross midnight split correctly
- Email a report to yourself or someone else (a mentor, for example)
- Data is stored locally in a SQLite file, never in the cloud

## Requirements

- Python 3.9 or newer
- An email account with SMTP access if you want emailed reports (Gmail works with an app password)

## Install

```
git clone https://github.com/faith1056/codetime.git
cd codetime
chmod +x codetime.py
mkdir -p ~/.local/bin
ln -sf "$PWD/codetime.py" ~/.local/bin/codetime
```

Make sure `~/.local/bin` is on your PATH. With zsh:

```
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

Check it works:

```
codetime status
```

## Usage

```
codetime start [project]    start the timer (project defaults to the folder name)
codetime status             show the running session and today's total
codetime stop               stop the timer
codetime stop --email       stop the timer and email today's report
codetime report [period]    show a report: today (default), week, month, or all
codetime report --email     also email the report
codetime setup              one-time email setup
```

Example:

```
cd ~/my-project
codetime start
# ... code for a while ...
codetime stop
codetime report week
```

Sample report:

```
Code time report: Week of Mon 26 Oct 2026

Total: 6h 40m across 4 session(s)

By project:
  campusflow  5h 10m
  codetime    1h 30m

By day:
  Mon 26 Oct  2h 05m
  Wed 28 Oct  3h 15m
  Sat 31 Oct  1h 20m
```

## Email setup

Run the setup once:

```
codetime setup
```

You will be asked for an SMTP server, port, login, password, and the address that should receive reports. To send to more than one person, separate the addresses with commas.

For Gmail:

1. Turn on 2-Step Verification in your Google account.
2. Create an app password at https://myaccount.google.com/apppasswords.
3. Use `smtp.gmail.com`, port `587`, your Gmail address, and the app password (not your normal password).

Work and school accounts often cannot create app passwords. In that case, use any other email service that offers SMTP.

Your settings are saved in `~/.codetime/config.env`, readable only by you. Never commit or share that file.

## Where your data lives

Everything is stored in `~/.codetime/`:

| File | Contents |
| --- | --- |
| `sessions.db` | your coding sessions |
| `config.env` | your email settings, including the password |

Set the `CODETIME_HOME` environment variable to use a different folder.

## Run the tests

```
python3 -m unittest discover tests
```

## Limitations

- It times only what you tell it to. There is no idle detection, so remember to run `codetime stop`.
- Sessions cannot be edited or deleted yet. If you forget to stop one, the totals will be too high (the app warns you when a session runs longer than 12 hours).
- Reports are sent only when you ask. There is no built-in schedule.

## Ideas for later

- [ ] `codetime stop --at 17:30` to correct a forgotten stop
- [ ] `codetime log` to list and delete sessions
- [ ] Scheduled weekly reports with cron

## Author

Built by [faith1056](https://github.com/faith1056).