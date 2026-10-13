# Day 0: step-by-step setup

Everything here is done by hand, before Claude Code writes any code. Budget about an hour, plus waiting time on the GPU quota request.

A note on the AWS console: Amazon moves menus around regularly. Instead of following menu paths, use the **search box at the top of the console** and type the service name ("IAM Identity Center", "Service Quotas", "Budgets"). That always works.

---

## 1. AWS account, root MFA, and a daily-use login

### 1a. Create the account

1. Go to <https://portal.aws.amazon.com/billing/signup>.
2. Enter an email address and an account name (e.g. `modelforge`). This email becomes the **root user**, the most powerful login on the account. Use an address you control permanently.
3. Verify the email with the code they send.
4. Set a strong root password and store it in a password manager.
5. Choose **Personal** account type, fill in your address and phone number.
6. Enter a credit or debit card. AWS charges a small temporary authorization (usually $1) and refunds it.
7. Verify your phone by SMS or voice call.
8. Choose the **Basic support plan** (free). Don't pick Developer or Business.

Activation takes a few minutes, occasionally a few hours. You'll get an email when it's ready.

### 1b. Turn on MFA for the root user

This is the single most important security step. An unprotected root account with a card attached is a real risk.

1. Sign in at <https://console.aws.amazon.com> with the root email.
2. Click your account name (top right) → **Security credentials**.
3. Find **Multi-factor authentication (MFA)** → **Assign MFA device**.
4. Name it `root-phone`, choose **Authenticator app**.
5. Scan the QR code with Google Authenticator, Authy, 1Password or similar.
6. Enter two consecutive codes to confirm.

Now sign out of root. From here on you use the account you create in the next step, and only return to root for billing changes or closing the account.

### 1c. Let non-root users see billing

Do this while still signed in as root, or you'll be confused later when your daily user can't open the budget page.

1. Account name (top right) → **Account**.
2. Scroll to **IAM user and role access to Billing Information** → **Edit** → tick **Activate IAM Access** → **Update**.

### 1d. Create a daily-use login with IAM Identity Center

IAM Identity Center (the service formerly called AWS SSO) gives you a login with an expiring session rather than permanent access keys. It's free, and it's what `aws configure sso` in step 3 connects to.

1. Still as root, search for **IAM Identity Center** in the console.
2. Set the region selector (top right) to **US East (N. Virginia) us-east-1** before enabling. The identity store lives in whichever region you enable it in and can't easily be moved.
3. Click **Enable**. If it asks about AWS Organizations, let it create one: that's normal and free.
4. On the dashboard, note the **AWS access portal URL**. It looks like `https://d-1234567890.awsapps.com/start`. Save it; you need it in step 3.
5. **Users** → **Add user**:
   - Username: `yourname`
   - Email: your email (can be the same as root, or a `+alias` variant)
   - First and last name
   - Click through to **Add user**. Skip adding groups.
6. You'll get an invitation email. Open it, accept, set a password, and register an MFA device (same process as root).
7. Back in IAM Identity Center → **Permission sets** → **Create permission set**:
   - **Predefined permission set** → **AdministratorAccess**
   - Session duration: 8 hours (the default 1 hour means re-logging in all day)
   - Name it `AdminAccess`, create it.
8. **AWS accounts** → tick your account → **Assign users or groups**:
   - Select your user → **Next**
   - Select the `AdminAccess` permission set → **Next** → **Submit**

Test it: open the access portal URL in a browser, sign in as your new user, and you should see your account with an `AdminAccess` role you can click into. That's the console you'll use from now on.

---

## 2. Install the tools

Check what you already have first:

```bash
aws --version      # want v2.x
docker --version
node --version     # want v20 or newer
python3 --version  # want 3.11 or newer
cdk --version
```

### macOS

```bash
# Homebrew, if you don't have it
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

brew install awscli node@20 python@3.11 git
brew install --cask docker     # then open Docker Desktop once to start the daemon
npm install -g aws-cdk
```

### Windows

Use PowerShell **as Administrator** with winget:

```powershell
winget install Amazon.AWSCLI
winget install OpenJS.NodeJS.LTS
winget install Python.Python.3.11
winget install Git.Git
winget install Docker.DockerDesktop
```

Then close and reopen PowerShell (so the PATH updates) and run:

```powershell
npm install -g aws-cdk
```

**Strongly consider WSL2 instead.** Much of this project (Docker worker images, `make`, shell scripts, llama.cpp builds) assumes a Unix environment. Run `wsl --install` in an Administrator PowerShell, reboot, then install Ubuntu and follow the Linux instructions inside it. Docker Desktop has a WSL2 integration setting to enable.

### Linux (Ubuntu/Debian)

```bash
# AWS CLI v2
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip
unzip awscliv2.zip && sudo ./aws/install && rm -rf aws awscliv2.zip

# Node 20 via nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
source ~/.bashrc && nvm install 20

sudo apt update && sudo apt install -y python3.11 python3.11-venv git
# Docker: follow https://docs.docker.com/engine/install/ubuntu/
sudo usermod -aG docker $USER   # then log out and back in

npm install -g aws-cdk
```

### Verify

```bash
aws --version && node --version && python3 --version && cdk --version && docker run --rm hello-world
```

All five should succeed. If `docker run` fails, Docker Desktop isn't running (macOS/Windows) or your user isn't in the `docker` group (Linux).

---

## 3. Connect the CLI, then bootstrap the CDK

### 3a. `aws configure sso`

Run it and answer the prompts:

```bash
aws configure sso
```

| Prompt | Answer |
|---|---|
| SSO session name | `modelforge` |
| SSO start URL | your access portal URL from step 1d, e.g. `https://d-1234567890.awsapps.com/start` |
| SSO region | `us-east-1` |
| SSO registration scopes | press Enter to accept `sso:account:access` |

A browser window opens asking you to confirm a code. Approve it. Back in the terminal:

| Prompt | Answer |
|---|---|
| Account | pick your account (arrow keys, Enter) |
| Role | `AdminAccess` |
| Default client region | `us-east-1` |
| CLI default output format | `json` |
| Profile name | `modelforge` |

Now set the profile for your shell and check it works:

```bash
export AWS_PROFILE=modelforge
aws sts get-caller-identity
```

You should see JSON containing your 12-digit **Account** number. Copy it; you need it next.

Add `export AWS_PROFILE=modelforge` to your `~/.zshrc` or `~/.bashrc` so you don't have to set it every session. On Windows PowerShell, use `$env:AWS_PROFILE = "modelforge"`.

**When your session expires** (after 8 hours) commands start failing with a token error. Fix it with:

```bash
aws sso login --profile modelforge
```

### 3b. `cdk bootstrap`

Bootstrapping creates a small set of resources the CDK needs to deploy anything: an S3 bucket for assets, an ECR repository for images, and a few IAM roles. It costs a few cents a month at most.

```bash
cdk bootstrap aws://123456789012/us-east-1 --profile modelforge
```

Replace `123456789012` with your real account number. It takes 1–2 minutes and ends with `✅ Environment aws://.../us-east-1 bootstrapped`.

If it complains Docker isn't running, start Docker Desktop and retry.

---

## 4. Request the GPU quota

New AWS accounts have a GPU instance quota of **zero**. Until this is raised you cannot run GPTQ, AWQ or distillation jobs, and approval can take anywhere from a few hours to several days. That's why it's a day 0 task.

1. In the console, search for **Service Quotas**.
2. Confirm the region (top right) is **us-east-1**.
3. **AWS services** → search for and open **Amazon Elastic Compute Cloud (Amazon EC2)**.
4. In the quota search box, type **"All G and VT Spot Instance Requests"**. Open it.
5. Click **Request increase at account level**.
6. Enter **8** as the new value. Submit.

The number is in **vCPUs, not instances**. A `g6.xlarge` has 4 vCPUs, so 8 lets you run two at once. That's plenty for development.

While you're there, also request **"Running On-Demand G and VT instances"** = 8. Spot capacity occasionally runs out in a region, and this gives you a fallback. Day 20 keeps the on-demand queue disabled by default, so you won't accidentally pay on-demand prices.

AWS may email asking what you need it for. A plain answer works: *"Running short GPU batch jobs for machine-learning model compression on a development project."*

You can carry on with days 1–18 while you wait. None of them need a GPU.

---

## 5. Set a $20 monthly budget

Do this before anything is deployed. It's your safety net against a misconfigured loop or a forgotten resource.

1. Sign in through the access portal as your `AdminAccess` user (billing access was enabled in step 1c).
2. Search for **Billing and Cost Management** → **Budgets** in the left menu → **Create budget**.
3. Choose **Use a template (simplified)** → **Monthly cost budget**.
4. Budget name: `modelforge-monthly`.
5. Enter **$20** as the amount.
6. Email recipients: your email address.
7. **Create budget**.

That template alerts you at 85% actual and 100% forecasted spend. To get exactly 50% and 100%, open the budget after creating it → **Alerts** tab → **Add alert threshold**:

- Alert 1: Actual cost, **50%** of budgeted amount, email you
- Alert 2: Actual cost, **100%** of budgeted amount, email you
- Alert 3 (worth adding): Forecasted cost, **100%**, email you. This one warns you early in the month if your spending rate would blow the budget.

Two more things worth turning on while you're in Billing:

- **Cost Explorer** (left menu → Cost Explorer → Enable). It takes 24 hours to populate, so switching it on now means the data is there when you need it on day 19.
- **Free tier alerts**: Billing preferences → tick the free-tier usage alert option.

---

## 6. Create the GitHub repo

### 6a. Make the repo

1. Go to <https://github.com/new>.
2. Repository name: `modelforge`.
3. Description (from the earlier message):
   `Compress and convert ML models in the browser. Quantization, pruning, distillation and low-rank factorization for PyTorch, ONNX, TFLite, Keras, safetensors and GGUF.`
4. **Private.** Make it public around day 19, after a security review.
5. Tick **Add a README file**. Leave .gitignore and license as None; we'll add a proper .gitignore in a moment.
6. **Create repository**.

### 6b. Clone and set up

```bash
git clone https://github.com/YOUR-USERNAME/modelforge.git
cd modelforge
mkdir -p docs
```

Now copy the two files you have into place:

```bash
# adjust the source paths to wherever you downloaded them
cp ~/Downloads/modelforge-v2.html docs/ui-prototype.html
cp ~/Downloads/README.md README.md          # the build guide, overwriting GitHub's placeholder
```

On Windows PowerShell, use `Copy-Item` instead of `cp`.

### 6c. The .gitignore, before your first commit

This matters. Model files are hundreds of megabytes, and once a large file or a secret is in git history it's painful to remove.

Create `.gitignore` with this content:

```gitignore
# Secrets
.env
.env.*
!.env.example
*.pem
aws-exports.js

# Python
__pycache__/
*.py[cod]
.venv/
venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/
*.egg-info/

# Node
node_modules/
dist/
build/
.vite/
coverage/
*.tsbuildinfo

# CDK
cdk.out/
.cdk.staging/

# Tooling output
.screenshots/
playwright-report/
test-results/
storybook-static/
.DS_Store

# Model and data files: never commit these
*.onnx
*.tflite
*.h5
*.hdf5
*.keras
*.pt
*.pth
*.bin
*.ckpt
*.safetensors
*.gguf
*.engine
*.mlpackage
/data/
/models/
```

Note that `!.env.example` keeps a committed template of which variables are needed, with no real values in it.

### 6d. First commit

```bash
git add .
git commit -m "Day 0: project setup, approved UI prototype, build plan"
git push
```

Check on GitHub that `docs/ui-prototype.html` is there and that no `.env` file got committed.

### 6e. Add the topics

On the repo page, click the gear icon next to **About** and paste these into the topics field:

```
machine-learning model-compression quantization pruning knowledge-distillation
onnx pytorch tensorflow-lite keras gguf llm edge-ai model-conversion
inference-optimization tensorrt openvino fastapi react aws serverless
```

---

## Verification checklist

Before starting day 1, confirm all of these:

- [ ] Root user has MFA, and you are no longer signed in as root
- [ ] You can sign in through the access portal URL as your daily user
- [ ] `aws sts get-caller-identity` prints your account number
- [ ] `cdk bootstrap` finished successfully
- [ ] `docker run --rm hello-world` works
- [ ] `node --version` is 20+, `python3 --version` is 3.11+
- [ ] The GPU quota request is submitted (approval can come later)
- [ ] The $20 budget exists and has your email on it
- [ ] The repo is cloned, `docs/ui-prototype.html` opens in a browser and works
- [ ] `.gitignore` is committed and `git status` is clean

Then, in the repo folder:

```bash
claude
```

and paste the Day 0 prompt from the README.

---

## Common problems

**`aws sso login` opens a browser that says "invalid request"** — the SSO start URL in `~/.aws/config` is wrong. Open that file, check the `sso_start_url` line against your access portal URL, and fix it.

**`cdk bootstrap` says "Need to perform AWS calls but no credentials configured"** — your SSO session expired or `AWS_PROFILE` isn't set. Run `aws sso login --profile modelforge` and `export AWS_PROFILE=modelforge`.

**The budget page says access denied** — step 1c wasn't done, or you did it while signed in as the daily user instead of root. Sign in as root and activate IAM access to billing.

**Docker commands need `sudo` on Linux** — you skipped `usermod -aG docker $USER`, or you did it but haven't logged out and back in since.

**Windows: `make` is not recognized** — the project uses a Makefile from day 1. Either work inside WSL2, or install make with `winget install GnuWin32.Make` and add it to your PATH. WSL2 is much less friction.
