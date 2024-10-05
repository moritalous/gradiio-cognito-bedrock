import os
import urllib

import boto3
import gradio as gr
import requests
import uvicorn
from fastapi import Depends, FastAPI, Request
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse

IDENTITY_POOL_ID = os.environ.get("IDENTITY_POOL_ID")

USER_POOL_ID = os.environ.get("USER_POOL_ID")
USER_POOL_REGION = os.environ.get("USER_POOL_REGION")

CLIENT_ID = os.environ.get("CLIENT_ID")
AUTHORIZATION_ENDPOINT = os.environ.get("AUTHORIZATION_ENDPOINT")

REDIRECT_URI = os.environ.get("REDIRECT_URI")
LOGOUT_URI = os.environ.get("LOGOUT_URI")

SECRET_KEY = os.environ.get("SECRET_KEY")

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)


def get_aws_credentials(id_token: str) -> dict:
    client = boto3.client("cognito-identity")

    response = client.get_id(
        IdentityPoolId=IDENTITY_POOL_ID, Logins={USER_POOL_ID: id_token}
    )

    identity_id = response["IdentityId"]

    response = client.get_credentials_for_identity(
        IdentityId=identity_id, Logins={USER_POOL_ID: id_token}
    )

    credentials = response["Credentials"]
    # credentials["AccessKeyId"]
    # credentials["SecretKey"]
    # credentials["SessionToken"]

    return credentials


def get_token(code: str):
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
    }

    body = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }

    response = requests.post(
        f"{AUTHORIZATION_ENDPOINT}/oauth2/token",
        headers=headers,
        data=body,
    )

    tokens = response.json()
    return tokens


# Dependency to get the current user
def get_user(request: Request):
    id_token = request.session.get("id_token")
    if id_token:
        return id_token
    return None


######
# root
######


@app.get("/")
def public(request: Request, id_token=Depends(get_user)):

    root_url = gr.route_utils.get_root_url(request, "/", None)

    if id_token:
        return RedirectResponse(url=f"{root_url}/main/")

    return RedirectResponse(url=f"{root_url}/top/")


######
# top
######


def LoginButton(value: str):
    btn = gr.Button(value=value)

    url = f"{AUTHORIZATION_ENDPOINT}/oauth2/authorize?client_id={CLIENT_ID}&response_type=code&scope=email+openid+phone&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"

    _js_redirect = """
    () => {
        url = '{url}';
        window.location.href = url;
    }
    """.replace(
        "{url}", url
    )

    btn.click(None, js=_js_redirect)

    return btn


with gr.Blocks() as top:
    btn = LoginButton(
        "Login",
    )

app = gr.mount_gradio_app(app, top, path="/top")

######
# main
######


def LogoutButton(value: str):
    btn = gr.Button(value=value)

    url = f"{AUTHORIZATION_ENDPOINT}/logout?client_id={CLIENT_ID}&logout_uri={urllib.parse.quote(LOGOUT_URI)}"

    _js_redirect = """
    () => {
        url = '{url}';
        window.location.href = url;
    }
    """.replace(
        "{url}", url
    )

    btn.click(None, js=_js_redirect)

    return btn


def main_fn(
    text: str,
    request: gr.Request,
):
    id_token = request.request.session["id_token"]
    credentials = get_aws_credentials(id_token)

    bedrock_client = boto3.Session(
        aws_access_key_id=credentials["AccessKeyId"],
        aws_secret_access_key=credentials["SecretKey"],
        aws_session_token=credentials["SessionToken"],
    ).client("bedrock-runtime")

    response = bedrock_client.converse(
        modelId="us.anthropic.claude-3-haiku-20240307-v1:0",
        messages=[{"role": "user", "content": [{"text": text}]}],
    )

    return response["output"]["message"]["content"][0]["text"]


with gr.Blocks() as main:
    logout_button = LogoutButton(value="Logout")

    main_interface = gr.Interface(
        main_fn, inputs=gr.Text(), outputs=gr.Text(), allow_flagging="never"
    )

app = gr.mount_gradio_app(app, main, path="/main", auth_dependency=get_user)

######
# Login callback
######


@app.get("/callback")
def get_callback(request: Request):
    root_url = gr.route_utils.get_root_url(request, "/", None)

    if "code" in request.query_params:
        code = request.query_params["code"]
        tokens = get_token(code)
        if "id_token" in tokens:
            request.session["id_token"] = tokens["id_token"]

    return RedirectResponse(url=f"{request.base_url}")


######
# logout
######
@app.get("/logout")
def get_logout(request: Request):
    if "id_token" in request.session:
        del request.session["id_token"]

    return RedirectResponse(url=f"{request.base_url}")


######


if __name__ == "__main__":
    uvicorn.run(app)
