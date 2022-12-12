### Preparation

1. Create a new Google Cloud project, with a **_verified_ billing account and payment method** linked to it.
2. Enable the following APIs for your Google Cloud project: **Cloud Vision**, **Google Drive**, **Google Sheets**.
3. Create a new **Service Account** for your Google Cloud project. If you can figure out the absolutely minimal role it should take to function correctly, then that's great!!! Otherwise just grant it the highest possible role (Owner) and guard it with your life, since it has access to your credit card now.
4. Create a new **JSON authentication key** for your Service Account. Upon creation, a **JSON file** representing the private key in the key pair will be downloaded to your computer.
5. Open this JSON file with a text editor and take note of the email in the **client_email** key.
6. Open the **STONK! sheet** and share **_Editor_ access** of the sheet with this email.
7. Setup a Discord bot in your Discord server with **_Message Content_ intent enabled** and the following Bot Permissions: **Read Messages/View Channels**, **Send Messages**, **Read Message History**, **Use External Emojis** (yes, this is Kaori important), **Add Reactions**.
8. Take note of your bot's **security token**.

### Installation & Running

Once you have completed all the steps above, setup a **Ubuntu 18.04** machine, clone this repository, stand at its root directory and run the following code:
```
./ocr-mechabridget.sh
```
**If this is your first time running it on a new machine**, the script will install the required packages and may prompt you for sudo password.
**After installation finishes**, the script will ask you to fill in the fields in a newly generated **config.local.ini** file before terminating. Open this file with a text editor and fill its empty fields with things you have noted down so far from the above section, including the **unique ID and worksheet's name of the STONK! sheet**.
**Once you have finished**, run the above code again.
