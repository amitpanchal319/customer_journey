import os
import requests,json
import mimetypes
import base64

# Azure AD app credentials — provided via environment (.env), never hard-coded.
AZURE_TENANT_ID     = os.getenv("AZURE_TENANT_ID", "")
AZURE_CLIENT_ID     = os.getenv("AZURE_CLIENT_ID", "")
AZURE_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET", "")


class SMTP:
    TOKEN_PATH = ''
    TOKEN = {}
    def __init__(self,username,token_path):
        self.SENDER=username
        self.TOKEN_PATH=token_path
        with open(self.TOKEN_PATH,'r') as f:
            self.TOKEN = json.loads(f.read())

    def _normalize_recipients(self, value):
        """
        Always return a LIST of valid email strings.
        Accepts string / list / tuple.
        """
        if not value:
            return []

        if isinstance(value, (list, tuple)):
            raw = value
        else:
            raw = str(value).replace(",", ";").split(";")

        clean = []
        for e in raw:
            e = str(e).strip()
            if "@" in e and "." in e:
                clean.append(e)

        return clean
    
    def get_access_token(self):
        
        token_req = requests.post(
            f"https://login.microsoftonline.com/{AZURE_TENANT_ID}/oauth2/v2.0/token",
            headers={
                'Content-Type':'application/x-www-form-urlencoded'
            },
            data={
                "client_id":AZURE_CLIENT_ID,
                "scope":"offline_access Mail.ReadWrite https://outlook.office.com/IMAP.AccessAsUser.All https://outlook.office.com/SMTP.Send",
                "refresh_token":self.TOKEN['refresh_token'],
                "grant_type":"refresh_token",
                "client_secret":AZURE_CLIENT_SECRET
            }
        )
        if token_req.status_code!=200:
            raise Exception(f"refresh Token invalid! {token_req.status_code} {token_req.text}")
        
        token_req = token_req.json()
        if "access_token" in token_req:
            self.TOKEN = {
                "access_token": token_req["access_token"],
                "refresh_token": token_req["refresh_token"],
            }
            with open(self.TOKEN_PATH, "w") as f:
                json.dump(self.TOKEN, f)

        return self.TOKEN["access_token"]
    
    def attachment_format(self,filePath):
        files = []
        for file in filePath:
            # print(file)
            mime_type = mimetypes.guess_type(file)[0]
            with open(file,'rb') as f:
                files.append(
                    {
                        "@odata.type": "#microsoft.graph.fileAttachment",
                        "name": file.split('\\')[-1],
                        "contentType": mime_type,
                        # "contentBytes": base64.urlsafe_b64decode(f.read())
                        "contentBytes": base64.b64encode(f.read()).decode('utf-8')
                    }
                )
        return files

    def send_msg(self, to, subject, msgType, msg, attachment, cc=None):
        cc = cc or []

       
        to_list = self._normalize_recipients(to)
        cc_list = self._normalize_recipients(cc)

        if not to_list:
            raise Exception("No valid TO recipients after normalization")

        formatted_attachments = self.attachment_format(attachment)

        email_msg = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": msgType,
                    "content": msg,
                },
                "toRecipients": [
                    {"emailAddress": {"address": r}} for r in to_list
                ],
                "ccRecipients": [
                    {"emailAddress": {"address": r}} for r in cc_list
                ],
                "attachments": formatted_attachments,
            },
            "saveToSentItems": True,
        }

        def _send():
            return requests.post(
            "https://graph.microsoft.com/v1.0/me/sendMail",
            headers={
                "Authorization": f"Bearer {self.TOKEN['access_token']}",
                "Content-Type": "application/json",
            },
            json=email_msg,
        )

        # 🔁 First attempt
        response = _send()

        # 🔐 Token expired → refresh silently
        if response.status_code == 401:
            self.get_access_token()
            response = _send()

        
        if response.status_code != 202:
            raise Exception(
                f"Email failed {response.status_code} -- {response.text}"
            )
