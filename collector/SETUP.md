# The live collector: today's RBN spots, running free on Google Cloud

RBN publishes a day's file only after the UTC day is over, so the app cannot show today's spots from it. The collector fills that gap. It stays
connected to RBN's live feed all day, keeps the last two days of spots, and answers one question for the app: *the spots of this callsign today*.

It has to run on a machine that is always on, so it cannot live on the Streamlit site (which sleeps when nobody is using it). A Google Cloud
**e2-micro** machine is free forever within its limits (checked November 2026; Google can change this), and is plenty: a quiet day is about
650,000 spots (about 40 MB stored) and a contest day about three times that.

Until the app is given the collector's address it works exactly as it always has. Nothing changes for anyone.

## What you do, once (about 20 minutes)

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

The page shows a monthly price estimate while you fill it in. With these settings the free allowance should bring it to $0, but check that the
estimate looks small before you click Create.

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

## How it behaves

- If the collector started part way through the day, or lost its connection for a while, the page says so above the map: for example *"the live
  collector only began listening at 09:41 UTC, so spots before that are missing."* The complete list is in RBN's daily file the next day, and the
  app uses that for any finished day.
- If the collector is down, the date goes back to ending at yesterday and Paste still works. Nothing breaks.
- The key keeps strangers from using the service. It is not a strong secret, since the collector only holds spots that RBN publishes anyway.

## Looking after it

Everything is in the browser terminal (click **SSH** again):

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

- **One free machine only.** Do not make a second e2-micro in the account, or it is charged.
- **1 GB a month of data out is free** (to anywhere in North America). Each answer is a few kilobytes, repeated requests are answered from a
  20-second memory, and each caller is limited to 120 requests a minute, so ordinary use stays far below that.
- **It only has spots from when it started.** It is a stand-in for today, not an archive. The daily file remains the record.
- **It collects the CW and RTTY feed** (port 7000), which is almost all of RBN's daily file. FT8 and FT4, which RBN carries on another feed, are not collected.
- **Privacy:** the callsigns people look up reach the collector. It does not store them; it only answers.
