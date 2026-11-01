# Hosting the workshop on a Nectar JupyterHub

This guide sets up a JupyterHub for the AEO 2026 workshop notebooks. Attendees only need a browser. The hub is [The Littlest JupyterHub](https://tljh.jupyter.org) (TLJH) running on one Nectar Research Cloud VM.

Each step is tagged:

- **[YOU]** Only you can do it (Nectar dashboard, accounts, DNS, decisions).
- **[DONE]** Already prepared in `hub/`. You just run or paste it.
- **[CHECK]** Not verifiable from here. Confirm it before relying on it.

## What's in `hub/`

| File | What it does |
| --- | --- |
| `cloud-init.yaml` | Paste into Nectar's *Customisation Script* at launch. Installs TLJH 2.0.0, clones this repo to `/opt/aeo-workshop-notebooks`, runs the three scripts below. |
| `install-env.sh` | Installs the workshop packages from conda-forge into the shared user environment (`/opt/tljh/user`). Reads the package list from `pixi.toml` (minus `nbstripout`), so there is no extra list to keep in sync. `--dry-run` prints the list. |
| `configure.sh` | Applies the hub settings with `tljh-config`: login, per-user limits, idle culler, JupyterLab as default, and HTTPS. Also hides `hub/` and the pixi/conda files from attendees' file browser. Settings are environment variables, documented at the top of the file. |
| `smoke_test.py` | Imports every package, reads the imagery from the STAC catalogue, computes indices and writes GeoTIFFs. Prints OK/FAIL per check. Passes locally under pixi; it reads 65 MB in about 13 s. |
| `nbgitpuller_link.py` | Prints the links you hand to attendees. |
| `Caddyfile`, `setup-caddy.sh` | Caddy in front of the hub: HTTPS for `dronescape.earth`, the `/aeo-workshop-notebooks` short link, and `stac.dronescape.earth` → the STAC catalogue. |

All scripts can be re-run safely.

## How it fits together

- **One VM, many users.** TLJH gives each attendee their own Linux account (`jupyter-<name>`), home folder and Jupyter server, capped by a RAM and CPU limit. Everyone shares one Python environment, so packages are installed once. TLJH suits up to roughly 100 users on one machine. For 15–50 attendees it is simpler than Kubernetes ([TLJH docs](https://tljh.jupyter.org/en/latest/)).
- **No shared data.** `workshop_utils.load_data()` reads a 65 MB window of the COG over HTTPS from Nectar Object Storage. Each kernel needs about 0.5–1.5 GB of RAM, depending on the chapter.
- **Notebooks arrive by link.** An [nbgitpuller](https://nbgitpuller.readthedocs.io) link logs the attendee in, copies the repo into their home folder and opens JupyterLab. Clicking it again pulls new commits and keeps the attendee's own edits.
- **Login.** One shared workshop password (JupyterHub's built-in `SharedPasswordAuthenticator`). Each attendee types a username of their choice (their first name, say) plus that password and gets their own home folder and server. Admins log in with a separate long admin password, so the workshop password can't be used to become admin. See [Decisions](#decisions-and-why).

---

## Part A — Before the workshop

### 1. [YOU] Answer the open questions

- [ ] How many attendees? This sets the VM size (step 3).
- [ ] When is the workshop, and how long should the hub stay up afterwards (for example, a week so people can download their work)?
- [ ] Hostname: a Nectar DNS name (`<something>.<project>.cloud.edu.au`, free) or a UTAS subdomain (ask UTAS IT)?
- [ ] Who else needs admin rights (co-instructors)?
- [ ] The workshop password (8+ characters, easy to read off a slide), or let setup generate one.

### 2. [YOU] Check your project's quota

Use your existing Nectar project. In the dashboard, open *Compute* → *Overview* (or *Allocations* → *My Allocations*) and check you have headroom for:

- **Cores and RAM** for the flavour in step 3. For example, 32 cores and 128 GB for an `r3.xxlarge`.
- **Service Units** for the hours the VM will run. See the estimate below.
- **A DNS zone** (usually `<project>.cloud.edu.au`), if you want the free Nectar hostname in step 7 ([Nectar DNS service](https://support.ehelp.edu.au/support/solutions/articles/6000201311-nectar-dns-service)). Without one, use a UTAS hostname instead.

If all of that fits, you can launch straight away. Only if you're short do you need to amend the allocation (*Allocations* → *Amend*). That goes through review, which Nectar says ["can take up to four weeks"](https://support.ehelp.edu.au/support/solutions/articles/6000068044-managing-an-allocation), so do it early in that case.

**[CHECK] Service Units.** Every flavour has an SU-per-hour cost listed in the [Nectar flavours article](https://support.ehelp.edu.au/support/solutions/articles/6000205341-nectar-flavors). The published rate for `r3.xsmall` (1 vCPU) is about 0.052 SU/h. That puts an `r3.xxlarge` (32 vCPU) at about 1.7 SU/h, or 40 SU/day, so two weeks of uptime is about 560 SU. This is extrapolated, so check the current table before you submit.

### 3. [YOU] Choose the VM size

RAM is the limit. Plan on about 2.5 GB per attendee working at the same time, plus 4 GB for the system. `MEM_LIMIT` is the most any one attendee can use; one person with all four chapters open can reach 3–4 GB. CPU is less critical: a shortage slows things down but doesn't crash anything ([TLJH resource estimation](https://tljh.jupyter.org/en/latest/howto/admin/resource-estimation.html)). Flavour specs are from the [Nectar flavours article](https://support.ehelp.edu.au/support/solutions/articles/6000205341-nectar-flavors).

| Attendees (+ instructors) | Flavour | vCPU | RAM | `MEM_LIMIT` | Notes |
| --- | --- | --- | --- | --- | --- |
| up to 15 | `r3.xlarge` | 16 | 64 GB | `4G` | Comfortable. `r3.large` (8 vCPU / 32 GB) works if people close kernels from earlier chapters. |
| up to 30 | `r3.xxlarge` | 32 | 128 GB | `4G` | Comfortable. |
| up to 50 | `r3.xxlarge` | 32 | 128 GB | `3G` | Tight (about 2.5 GB each). Tell attendees to shut down the previous chapter's kernel. For more headroom, run **two** hubs and split the room by link, or ask Nectar for an `h3` large-memory flavour (restricted, needs justification). |

All r3 flavours have a 30 GB root disk. That holds the environment (a few GB) and 50 attendees' `outputs/` folders (tens of MB each), so you don't need a separate volume. `m3` flavours have half the RAM per core of `r3`, so they suit this workload less well.

**[CHECK]** The flavours article says t3/m3/r3/c3 are available to all projects, but another Nectar page says r3 must be requested on the allocation form. If `r3` doesn't appear in the launch dialog, add it to your allocation request.

### 4. [DONE] Push this repo to a public git host

Pushed to <https://github.com/UTAS-TerraLuma/aeo-workshop-notebooks> (public), with the nbstripout filter installed so notebook outputs never get committed. On any other clone, run `pixi run setup-git` once before committing.

The hub always pulls whatever is on `main`, so push fixes there.

### 5. [YOU] Create a security group

Dashboard → *Project → Network → Security Groups* → *Create Security Group*. Name it `jupyterhub` and add three ingress rules ([Nectar security groups tutorial](https://tutorials.rc.nectar.org.au/sec-groups-101/03-create)):

| Rule | Port | CIDR | Why |
| --- | --- | --- | --- |
| SSH | 22 | your office/VPN range, or `0.0.0.0/0` | Admin access |
| HTTP | 80 | `0.0.0.0/0` | Let's Encrypt validation and the redirect to HTTPS |
| HTTPS | 443 | `0.0.0.0/0` | Attendees |

If you know the venue's public IP range, you can restrict 80/443 to it plus your own. Let's Encrypt still needs to reach port 80 or 443 to issue the certificate, so open them to everyone while you get it.

You also need an **SSH key pair** (*Project → Compute → Key Pairs*) if you don't already have one.

### 6. [YOU] Fill in and launch the VM

1. Copy `hub/cloud-init.yaml` and edit the block marked `CHANGE THESE`:
   - `ADMIN_USER`: your hub login, for example `jgregory`. Lower case, no spaces.
   - `REPO_URL`: the GitHub URL from step 4.

   Don't put passwords in this file; setup generates them (step 7). Anyone on the VM, attendees included, can read it from the cloud metadata service.
2. Dashboard → *Project → Compute → Instances* → **Launch Instance**:
   - **Source:** the official Nectar **Ubuntu 24.04 LTS (Noble) amd64** image. TLJH 2.0.0 tests on Ubuntu 22.04 and 24.04 and Debian 11 and 12. Ubuntu 20.04 is not supported.
   - **Flavour:** from step 3.
   - **Availability zone:** a Tasmanian zone (for example `tasmania`) if your allocation allows it. Use whatever the AZ list shows. **[CHECK]** the exact zone names and that the flavour has capacity there. Leaving it on "Any" also works.
   - **Networks:** **[CHECK]** Most Nectar zones give instances a public IPv4 address directly through the classic provider network. If yours only has a private network, you also need a floating IP.
   - **Security groups:** `jupyterhub` (from step 5).
   - **Key pair:** yours.
   - **Configuration → Customisation Script:** *Direct Input*, then paste the edited `cloud-init.yaml`.
3. Launch. Note the instance's IP address.

**[DONE]** cloud-init then runs everything else. It takes roughly 15–25 minutes. Watch it with:

```bash
ssh ubuntu@<ip> 'sudo tail -f /var/log/aeo-hub-setup.log'
```

It's finished when the log says `AEO hub setup finished` and ends with the smoke test's `ALL OK`. While TLJH installs, `http://<ip>` shows a progress page.

### 7. [YOU] Get the passwords and log in as admin

Setup generated two passwords. Read them with:

```bash
ssh ubuntu@<ip> 'sudo cat /root/admin-password.txt /root/workshop-password.txt'
```

Open `http://<ip>` and log in as `ADMIN_USER` with the **admin** password (the first line). To choose your own workshop password instead of the generated one:

```bash
ssh ubuntu@<ip>
sudo WORKSHOP_PASSWORD='<your-password>' bash /opt/aeo-workshop-notebooks/hub/configure.sh
```

It's kept on later runs, so you only set it once.

Add co-instructors as admins. They log in with the same admin password:

```bash
sudo tljh-config add-item users.admin <name>
sudo tljh-config reload
```

Hub admins get `sudo` on the VM, so only make people you trust admins.

### 8. [YOU] Point dronescape.io and dronescape.earth at the VM

Both domains are registered with Namecheap and use its DNS. **Hand out `dronescape.io`**: the UTAS network's web filter resets HTTPS connections to `dronescape.earth` (seen 30 Oct 2026), but not to `dronescape.io`. If the workshop is on UTAS Wi-Fi, ask UTAS IT to allowlist `dronescape.earth` too, or just don't use it.

In Namecheap: *Domain List → <domain> → Manage → Advanced DNS → Add New Record*. For each domain:

| Type | Host | Value | TTL |
| --- | --- | --- | --- |
| A Record | `@` | the VM's public IP | Automatic (or 5 min) |
| A Record | `stac` | the VM's public IP | Automatic (or 5 min) |
| A Record | `www` | the VM's public IP (`dronescape.io` only; it redirects to `dronescape.io`) | Automatic (or 5 min) |

Remove any parking-page records Namecheap added for `@` (a *URL Redirect* or a CNAME for `www`/`@`). Check from your laptop: `nslookup dronescape.io`, `nslookup stac.dronescape.io` (and the `.earth` names) should all return the VM's IP.

If the VM's IP ever changes (a new VM, or a resize that changes it), update these records. Caddy then gets new certificates by itself.

### 9. [DONE] Turn on HTTPS with Caddy

`hub/Caddyfile` makes Caddy (as used for naturescan) serve, on both `dronescape.io` and `dronescape.earth`:

- `https://dronescape.io`: the hub.
- `https://dronescape.io/aeo-workshop-notebooks`: the short link for attendees. It redirects to the nbgitpuller link, which logs them in, pulls the notebooks and opens JupyterLab.
- `https://stac.dronescape.io`: the STAC catalogue, passed through from Nectar object storage. `/` goes to `catalog.json`.

Once the names resolve, on the VM (re-run it after any Caddyfile change):

```bash
cd /opt/aeo-workshop-notebooks && sudo git pull
sudo bash hub/setup-caddy.sh
```

It moves TLJH from ports 80/443 to port 8000 (the security group keeps 8000 closed to the outside), installs Caddy and starts it. After a minute, all three addresses above should load with a padlock. Caddy log: `sudo journalctl -u caddy -f`.

Don't also use `configure.sh`'s `HTTPS_DOMAIN` option: Caddy owns HTTPS now, and `configure.sh` refuses if you try.

The notebooks still read the imagery straight from the object-store URL, not through `stac.dronescape.earth`. That way they keep working after this VM is gone. `stac.dronescape.earth` only works while this VM is running; for a permanent name, move the `stac.dronescape.earth` block of the Caddyfile to a small long-lived VM (or the naturescan server).

### 10. [DONE] The attendee link

Hand out **`https://dronescape.io/aeo-workshop-notebooks`**. For links that open a specific chapter, run on your laptop:

```bash
python hub/nbgitpuller_link.py https://dronescape.io https://github.com/UTAS-TerraLuma/aeo-workshop-notebooks
```

### 11. [YOU] Test as an attendee

1. In a private/incognito window, open the link and log in as `test01` with the workshop password.
2. JupyterLab should open on `aeo-workshop-notebooks/`. In each chapter run **Kernel → Restart Kernel and Run All Cells**, then check that:
   - the imagery loads (Chapter 1's first data cell),
   - the widgets, sliders, Plotly figures and Folium maps respond,
   - files appear in `aeo-workshop-notebooks/outputs/`.
3. The memory indicator in the JupyterLab status bar shows usage against the limit. Note the peak for each chapter. It tells you whether `MEM_LIMIT` fits.
4. Delete `test01` afterwards on the Admin page (*Edit User* → **Delete User**).

### 12. [YOU] Load test (a few days before)

**With real browsers (best):** have 3–5 colleagues log in with their own names and the workshop password and run chapters 1–4 at once. Meanwhile, on the VM:

```bash
watch -n 2 free -h          # total RAM in use
sudo systemd-cgtop          # RAM/CPU for each jupyter-<user> service
```

**Headless, more load:** run every chapter in N parallel copies. This runs as root, outside the per-user limits, so it only measures total RAM, CPU and network:

```bash
N=10
for i in $(seq $N); do
  ( d=/tmp/nbtest$i; rm -rf $d; cp -r /opt/aeo-workshop-notebooks $d; cd $d
    /opt/tljh/user/bin/jupyter nbconvert --to notebook --execute \
      --ExecutePreprocessor.timeout=1200 --output-dir $d/executed CHAPTER*.ipynb \
      > $d/log.txt 2>&1; echo "copy $i exit $?" ) &
done; wait
rm -rf /tmp/nbtest*
```

Any exit status other than 0 means a chapter failed. Read `/tmp/nbtestN/log.txt` before the `rm`. Peak `free -h` over N copies × (number of attendees ÷ N) gives a rough worst case.

### 13. [YOU] Put the link and password on a slide

Show `https://dronescape.io/aeo-workshop-notebooks` (or a QR code) and the workshop password. Tell attendees: "Log in with your first name, in lower case, and this password. Use the same name every time, or you'll get an empty folder."

---

## Part B — Workshop day

### Checklist

- [ ] An hour before: `https://<hub>` loads. Log in as admin and open **Admin** (`/hub/admin`).
- [ ] `ssh` in and run `/opt/tljh/user/bin/python /opt/aeo-workshop-notebooks/hub/smoke_test.py`. It should print `ALL OK`, confirming the STAC catalogue is reachable today.
- [ ] `free -h` shows plenty of free RAM. Restart any leftover test servers from the Admin page.
- [ ] Link and password slide ready. Have the admin page open on your laptop.
- [ ] Remind attendees: **one chapter at a time**. Before starting the next chapter, shut down the previous kernel (*Kernel → Shut Down Kernel*, or the *Running Terminals and Kernels* side panel). Each open notebook holds its own copy of the data.

### Admin page (`https://<hub>/hub/admin`)

- See who's logged in and whose server is running.
- **Stop Server / Start Server** for one attendee: fixes a frozen JupyterLab.
- **Access Server** opens the attendee's JupyterLab as them, so you can see what they see.
- Walk-ins need nothing: any new username with the workshop password gets an account.

### Resetting a user

- **"My files are gone":** they almost certainly logged in under a different name (`James` and `james` are different). Ask what name they used first.
- **Broken notebook:** the attendee deletes (or renames) the notebook and clicks the link again. nbgitpuller restores missing files from the repo.
- **Start completely fresh** (keeps a backup):

  ```bash
  sudo mv /home/jupyter-user07/aeo-workshop-notebooks /home/jupyter-user07/aeo-old-$(date +%H%M)
  ```

  Then they click the link again.
- **"Kernel restarting / the kernel appears to have died":** the attendee probably hit `MEM_LIMIT`. They should shut down other kernels and re-run. To raise the limit for everyone: `sudo MEM_LIMIT=5G bash /opt/aeo-workshop-notebooks/hub/configure.sh`. The new limit applies to servers started after the change.

### Watching the machine

```bash
free -h                                   # RAM
htop                                      # CPU per process
sudo systemd-cgtop                        # per attendee
sudo journalctl -u jupyterhub -f          # hub log: logins, spawns, errors
sudo journalctl -u jupyter-user07 -f      # one attendee's server log
```

---

## Part C — Troubleshooting

| Symptom | Check / fix |
| --- | --- |
| Log at `/var/log/aeo-hub-setup.log` stops early or missing | `sudo less /var/log/cloud-init-output.log`. Fix the cause (for example, `CHANGE_ME` left in, or repo not public), then `sudo bash /root/aeo-hub-setup.sh`. It's safe to re-run. |
| `Fill in the CHANGE_ME values` in the log | Edit `/root/aeo-hub-setup.sh` on the VM, then re-run it as above. |
| Can't reach `http://<ip>` at all | Security group has 80/443; the instance has a public IP (or floating IP); `sudo systemctl status caddy jupyterhub traefik`. |
| "Spawn failed" / server won't start | `sudo journalctl -u jupyterhub -n 100`. If the user environment broke, re-run `sudo bash /opt/aeo-workshop-notebooks/hub/install-env.sh`. Its last lines check that `jupyterhub-singleuser` still works. |
| `load_data()` fails / STAC errors | `curl -I https://object-store.rc.nectar.org.au/v1/AUTH_4df2f67c2eed48a2aaeeed008a4bf0de/aeo2026-workshop/collection.json` from the VM. Should be `200`. If not, check [Nectar status](https://status.rc.nectar.org.au). |
| HTTPS doesn't come up | Both names resolve to the VM (`getent hosts dronescape.earth stac.dronescape.earth` on the VM); ports 80/443 open; `sudo journalctl -u caddy -n 100`. |
| Login says invalid username/password | Wrong workshop password (`sudo cat /root/workshop-password.txt`). An admin username only works with the admin password. |
| Everything slow | `htop`: if the CPU is pegged, lower `CPU_LIMIT` or resize. If RAM is nearly full, ask people to shut down idle kernels. |
| Need a package added | Add it to `pixi.toml` (and the other env files) and push. Then on the VM: `cd /opt/aeo-workshop-notebooks && sudo git pull && sudo bash hub/install-env.sh`. Attendees restart their kernel. |
| Notebooks updated on GitHub | Attendees click the link again. nbgitpuller merges and keeps their edits. |

**Fallback if the hub is down:** GitHub Codespaces. Attendees click the *Open in GitHub Codespaces* button in the README and get JupyterLab with the same environment, on their own GitHub account's free allowance. Each attendee needs a GitHub account, so mention it in the pre-workshop email. Set up a prebuild beforehand so codespaces start in seconds (see *GitHub Codespaces → Prebuilds* in the README), and test it before the day.

[mybinder.org](https://mybinder.org) can also build from this repo's `environment.yml`, but its free sessions usually have only 1–2 GB of RAM and can be slow to start, which is likely too little for the later chapters. Treat it as a last resort.

---

## Part D — Afterwards

1. **[YOU] Give people time to download.** Leave the hub up for a few days if you promised to. In JupyterLab, right-click a file → *Download*.
2. **[YOU] Optional snapshot:** *Instances* → *Create Snapshot*. This stores the whole VM, including attendee home folders, as an image you can relaunch for a repeat workshop. Snapshots count against your image storage quota. You don't strictly need one, because `cloud-init.yaml` rebuilds the hub from scratch.
3. **[YOU] Stop paying SUs:** **delete** the instance (or **shelve** it if you want it back soon). **[CHECK]** Shelving is usually what stops SU consumption on Nectar; *Shut Off* may still count. Confirm in the Nectar SU docs.
4. **[YOU] Clean up:** delete the DNS record (*DNS → Zones → record → Delete*) and any floating IP. If any attendee data is sensitive, delete the snapshot when you no longer need it.

---

## Decisions and why

- **TLJH, not Kubernetes (Z2JH):** one VM, no cluster to manage, and the right scale for ≤50 users. Kept from the earlier analysis.
- **TLJH 2.0.0 (pinned):** the latest release (October 2024; no newer release as of October 2026). It tests on Ubuntu 22.04/24.04 and Debian 11/12, and ships JupyterHub 5. Its user environment is Python 3.12, the same as `pixi.toml` ([changelog](https://tljh.jupyter.org/en/latest/reference/changelog.html)).
- **Packages via `mamba` from conda-forge into `/opt/tljh/user`,** as TLJH documents for GDAL-based packages ([TLJH user environment](https://tljh.jupyter.org/en/latest/howto/user-env/user-environment.html)). `install-env.sh` reads `pixi.toml`, so the hub can't drift from the local setup. TLJH installs JupyterLab, ipywidgets and nbgitpuller with pip, and conda then installs its own JupyterLab and ipywidgets over them. Mixing pip and conda like this normally works, and `install-env.sh` checks the hub's pieces afterwards.
- **One shared password, separate usernames.** Literally one shared username would put everyone in the same home folder and the same Jupyter server, overwriting each other's work, so each attendee picks their own name. JupyterHub's built-in `SharedPasswordAuthenticator` (JupyterHub 5.3+; `configure.sh` makes sure the hub has it) is used rather than TLJH's DummyAuthenticator, because it gives admins their own 32+ character password. With DummyAuthenticator, anyone with the workshop password could log in as the admin, and TLJH admins have `sudo` on the VM. The trade-offs: anyone with the workshop password can log in as any other attendee, and anyone who finds the URL and the password can start a server. For 10–15 people on a one-day hub that's fine; change the password (`WORKSHOP_PASSWORD=...`) after the workshop if the hub stays up.
- **`hub/` hidden from attendees, not removed.** nbgitpuller copies the whole repo, so attendees get `hub/` too. It holds no secrets (passwords are generated on the VM into root-only files) and the repo is public anyway, so this is only to keep their file browser tidy. `configure.sh` sets Jupyter Server's `ContentsManager.hide_globs` in `/opt/tljh/user/etc/jupyter/jupyter_server_config.d/aeo-hide.json`; the files still open by path and from a terminal. It applies to servers started after the change.
- **Idle culler at 2 h, not TLJH's 10-minute default.** With the default, every server would be stopped (losing kernel state) during morning tea or lunch.
- **`MEM_LIMIT` 4G / `CPU_LIMIT` 2:** one chapter's kernel uses up to about 1.5 GB, so 4G covers two kernels at once plus the Jupyter server. When someone goes over, only their kernel restarts, not the whole machine.
- **No Dask, no jupyter-server-proxy:** Dask is being removed from the notebooks, so there's no dashboard to proxy.

## Still unverified

- That everything works end to end on a real Nectar VM. Shell syntax is checked (`bash -n`) and the smoke test passes locally, but nothing has run on Ubuntu or TLJH.
- Nectar availability zone names for Tasmania, whether `r3` needs requesting, whether the VM gets a public IP directly, SU rates, and whether shelving stops SU charges (marked [CHECK] above).
- Peak RAM per attendee under real use. Measure it in steps 11–12 and adjust `MEM_LIMIT` and the flavour.
- Whether headless `nbconvert --execute` gets through every chapter. A cell that needs user interaction would stop it. Browser testing (step 11) is the real test.

## Sources

- TLJH: [install on your own server](https://tljh.jupyter.org/en/latest/install/custom-server.html), [installer options](https://tljh.jupyter.org/en/latest/topic/customizing-installer.html), [requirements](https://tljh.jupyter.org/en/latest/topic/requirements.html), [tljh-config](https://tljh.jupyter.org/en/latest/topic/tljh-config.html), [idle culler](https://tljh.jupyter.org/en/latest/topic/idle-culler.html), [HTTPS](https://tljh.jupyter.org/en/latest/howto/admin/https.html), [FirstUse auth](https://tljh.jupyter.org/en/latest/howto/auth/firstuse.html), [resource estimation](https://tljh.jupyter.org/en/latest/howto/admin/resource-estimation.html), source code for v2.0.0 on [GitHub](https://github.com/jupyterhub/the-littlest-jupyterhub/tree/2.0.0) (config defaults in `tljh/configurer.py`)
- nbgitpuller: [URL options](https://nbgitpuller.readthedocs.io/en/latest/topic/url-options.html)
- Nectar: [flavours](https://support.ehelp.edu.au/support/solutions/articles/6000205341-nectar-flavors), [managing an allocation](https://support.ehelp.edu.au/support/solutions/articles/6000068044-managing-an-allocation), [teaching and training](https://support.ehelp.edu.au/support/solutions/articles/6000168216-using-nectar-for-teaching-and-training), [DNS service](https://support.ehelp.edu.au/support/solutions/articles/6000201311-nectar-dns-service), [DNS tutorial](https://tutorials.rc.nectar.org.au/dns/05-create-recordset), [security groups tutorial](https://tutorials.rc.nectar.org.au/sec-groups-101/03-create)
