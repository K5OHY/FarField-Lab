# The live collector: today's RBN spots

RBN publishes a day's file only after the UTC day is over, so the app cannot show today's spots from it. The collector fills that gap. It stays
connected to RBN's live feed all day, keeps the last two days of spots, and answers one question for the app: *the spots of this callsign today*.

To serve the website it has to run on a machine that is always on, so it cannot live on the Streamlit site (which sleeps when nobody is using it). A Google Cloud
**e2-micro** machine is free forever within its limits (checked November 2026; Google can change this), and is plenty: a quiet day is about
650,000 spots (about 40 MB stored) and a contest day about three times that.

Until the app is given the collector's address it works exactly as it always has. Nothing changes for anyone.

## Which way to run it

| | Where it runs | Always on | Can the website use it | Setup |
| --- | --- | --- | --- | --- |
| **A. Google Cloud** | A free machine in Google's data centre | Yes | **Yes** | About 20 minutes, needs a Google account and a card |
| **B. Raspberry Pi or other Linux box** | A small computer at home | Yes, if you leave it on | Only the app on your home network | About 10 minutes |
| **C. Windows** | Your own PC | Only while it is on, awake, and the window is open | Only the app on that PC | A few minutes |
| **D. Mac or Linux desktop** | Your own computer | Same as Windows | Only the app on that computer | A few minutes |

All of them are free. Only A can feed the Streamlit website, because the website runs on someone else's computer and cannot see yours or your home
network. If you only use the app on your own computer, C or D is the quickest, and B keeps it running while the computer is off. You can run
more than one.

## Option A: on Google Cloud (about 20 minutes, once)

### 1. A Google Cloud account

1. Go to <https://console.cloud.google.com> and sign in with a Google account.
2. Accept the free trial / set up billing when asked. A card is needed to prove who you are. The machine below is inside the always-free
   allowance, so it should cost nothing.
3. Make a project (any name, for example `farfield-rbn`).
4. **Set a spending alert** so there are no surprises: Billing, then Budgets & alerts, then Create budget. A budget of $1 with email alerts is enough.

### 2. The machine

Compute Engine, then VM instances, then **Create instance**, and set exactly this:

| Setting | Choose |
| --- | --- |
| Name | `rbn-collector` |
| Region | **us-central1 (Iowa)**, **us-west1 (Oregon)** or **us-east1 (South Carolina)**. Only these three are free. |
| Machine type | **E2**, then **e2-micro** |
| Boot disk | Change it to **Debian 12**, disk type **Standard persistent disk**, size **30 GB** (not Balanced, not SSD) |
| Firewall | Tick **Allow HTTP traffic** and **Allow HTTPS traffic** |

The page shows a monthly price estimate while you fill it in. It may show about $6 a month for the machine, because the preview does not apply
the always-free allowance; the allowance is taken off on the bill. The disk should show $0.00. Keep the $1 budget alert from step 1, and look at
Billing, then Reports, grouped by SKU, after a day or two to confirm the machine is charged nothing.

### 3. Install the collector

In the machine list, click **SSH** beside `rbn-collector`. A terminal opens in the browser. Paste:

```
sudo apt-get update && sudo apt-get install -y git
git clone --depth 1 --branch main https://github.com/K5OHY/FarField-Lab.git /tmp/setup
sudo bash /tmp/setup/collector/setup_vm.sh K5OHY
```

(Replace `K5OHY` with the callsign to log in to the feed with. If the collector is still only on the `beta` branch, use `--branch beta` in the
second line and `sudo BRANCH=beta bash ...` in the third.)

It takes a couple of minutes. At the end it prints two lines like:

```
LIVE_RBN_URL = "https://34-12-56-78.sslip.io"
LIVE_RBN_KEY = "0f3a..."
```

and a line showing the collector's health, which should say `"connected":true` within a few seconds.

### 4. Give the app those two lines

In Streamlit Community Cloud, open the app (try the beta one first), then Settings, then **Secrets**, and paste the two lines. Save. The app restarts.

On **My spots**, with RBN and Download a day, the date can now be today.

## Option B: a Raspberry Pi or other Linux box at home (about 10 minutes)

Any always-on Linux machine will do: a Raspberry Pi (any model with Raspberry Pi OS or another Debian-based system), an old laptop, a home
server. The collector is one Python file with no extra packages, so it is very light. This was written for Raspberry Pi OS and has not been tried
on a real Pi, so tell me if a step does not work.

In a terminal on the Pi (over SSH or at its keyboard), install what is needed and fetch the collector:

```
sudo apt-get update && sudo apt-get install -y git python3
git clone --depth 1 --branch main https://github.com/K5OHY/FarField-Lab.git ~/FarField-Lab
```

(If the collector is still only on the `beta` branch, use `--branch beta`.) Make it start by itself, and restart if it stops. Replace `K5OHY`
with your callsign (use for example `K5OHY-2` if another collector is already logged in with that callsign):

```
sudo tee /etc/systemd/system/rbn-collector.service >/dev/null <<EOF
[Unit]
Description=Live RBN spot collector
After=network-online.target
Wants=network-online.target

[Service]
User=$USER
ExecStart=/usr/bin/python3 $HOME/FarField-Lab/collector/rbn_service.py --call K5OHY --db $HOME/spots.db --bind 0.0.0.0 --port 8080
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now rbn-collector
curl -s http://127.0.0.1:8080/health
```

The last line should show `"connected":true` within a few seconds. `--bind 0.0.0.0` lets other computers on your home network reach it; use
`--bind 127.0.0.1` if the app runs on the Pi itself.

Now tell the app where it is. Find the Pi's address with `hostname -I` (say it prints `192.168.1.50`). On the computer that runs the app, set
`LIVE_RBN_URL` to `http://192.168.1.50:8080` before starting it, as in Option C (Windows) or D (Mac or Linux) below, but with that address. If
the app runs on the Pi itself, use `http://127.0.0.1:8080`.

Looking after it: `sudo journalctl -u rbn-collector -n 50` shows its log, `sudo systemctl restart rbn-collector` restarts it, and
`git -C ~/FarField-Lab pull && sudo systemctl restart rbn-collector` updates it. Your spots are in `~/spots.db`.

Two cautions. The collector writes to its database all day, which wears an SD card over months, so a USB drive or SSD is kinder if the Pi is to run
for years. And it is reachable from your home network only; to let the website reach it you would have to open your router to the internet, which
this guide does not cover. Use Option A for that.

## Option C: a Windows computer (a few minutes)

You need the app set up on your computer first (the README's *Run it locally* section). The collector needs nothing more than
Python, which you already have for that. It uses no extra packages.

Use two PowerShell windows, both opened in the `FarField-Lab` folder.

**Window 1: the collector.** Start it and leave the window open:

```
python collector\rbn_service.py --call K5OHY --db spots.db
```

(Use your own callsign. If the Google Cloud collector is also running with the same callsign, use a different login here, for example
`--call K5OHY-2`, so the two logins do not collide. That form connects fine.) After a few seconds it prints `connected to telnet.reversebeacon.net:7000`.
To check it, open <http://127.0.0.1:8080/health> in a browser: it should say `"connected":true`.

**Window 2: the app.** Tell the app where the collector is, then start it as usual:

```
$env:LIVE_RBN_URL = "http://127.0.0.1:8080"
.venv\Scripts\streamlit run web.py
```

No key is needed, because the collector listens only to your own computer. The first line has to be run in the same window as the second, every time
you open a new window. On **My spots**, with RBN and Download a day, the date can now be today.

Things that differ from Google Cloud:

- **It only collects while it runs.** If you close the window, put the computer to sleep or lose the internet, it stops listening. The page says
  when it began and which stretches are missing, so you are never shown a partial day as if it were complete. The complete list is in RBN's daily file the next day.
- **Restarting keeps the day.** The spots are saved in `spots.db` in that folder (48 hours, and git ignores the file). Run the same command
  again and it carries on; the time it was off shows up as a gap.
- **Stop it** with Ctrl+C in window 1.
- **The website cannot see it.** `127.0.0.1` means "this computer". The Streamlit website is on someone else's computer, so for it you need Option A.

## Option D: a Mac or Linux desktop (a few minutes)

The same as Option C, with Mac and Linux commands. Use two terminal windows in the `FarField-Lab` folder.

Window 1, the collector (leave it open):

```
python3 collector/rbn_service.py --call K5OHY --db spots.db
```

Window 2, the app (set up as in the README's *Run it locally* section):

```
export LIVE_RBN_URL="http://127.0.0.1:8080"
.venv/bin/streamlit run web.py
```

Everything in the notes under Option C applies: it only collects while it runs, restarting keeps the day, Ctrl+C stops it, and the website cannot see it.

## How it behaves

- If the collector started part way through the day, or lost its connection for a while, the page says so above the map: for example *"the live
  collector only began listening at 09:41 UTC, so spots before that are missing."* The complete list is in RBN's daily file the next day, and the
  app uses that for any finished day.
- If the collector is down, the date goes back to ending at yesterday and Paste still works. Nothing breaks.
- The key keeps strangers from using the service. It is not a strong secret, since the collector only holds spots that RBN publishes anyway.

## Looking after it

For Option A, everything is in the browser terminal (click **SSH** again). For a Pi, see the end of Option B.

| To | Run |
| --- | --- |
| See if it is healthy | `curl -s http://127.0.0.1:8080/health` |
| Read its log | `sudo journalctl -u rbn-collector -n 50` |
| Restart it | `sudo systemctl restart rbn-collector` |
| Update it to the latest code | `sudo bash /tmp/setup/collector/setup_vm.sh K5OHY` after `git -C /tmp/setup pull` (your key and data are kept) |
| Stop it | `sudo systemctl stop rbn-collector` |

If you ever stop and start the machine, Google may give it a new public address. Run the setup command again and paste the new `LIVE_RBN_URL`
into the app's secrets.

## Limits to know about

- **Option A: one free machine only.** Do not make a second e2-micro in the account, or it is charged.
- **1 GB a month of data out is free** (to anywhere in North America). Each answer is a few kilobytes, repeated requests are answered from a
  20-second memory, and each caller is limited to 120 requests a minute, so ordinary use stays far below that.
- **It only has spots from when it started.** It is a stand-in for today, not an archive. The daily file remains the record.
- **It collects the CW and RTTY feed** (port 7000), which is almost all of RBN's daily file. FT8 and FT4, which RBN carries on another feed, are not collected.
- **Privacy:** the callsigns people look up reach the collector. It does not store them; it only answers.
