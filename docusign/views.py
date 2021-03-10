# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import os
from django.shortcuts import HttpResponse
from django.urls import reverse
from django.http import HttpResponseRedirect
import requests
from os import path
from django.templatetags.static import static
from django.conf import settings
from datetime import datetime, timedelta
import json
from datetime import datetime
from django.views.generic import View
import base64
from docusign_esign import *
import jwt
from poc_docusign.docusign_config import CLIENT_AUTH_ID, USER_ID, ACCOUNT_ID, PRIVATE_KEY, BASE_URL, REST_API_BASE_URL

# Create your views here.
'''
Method to authenticate docusign programatically
Returns a jwt which is further required to make api calls
'''


def authenticate_docusign():
    message = {
        'iss': CLIENT_AUTH_ID,
        'sub': USER_ID,
        'iat': datetime.utcnow(),
        'exp': datetime.now() + timedelta(minutes=2),
        "aud": "account-d.docusign.com",
        "scope": "signature impersonation"
    }
    docusign_jwt = jwt.encode(message, PRIVATE_KEY, algorithm="RS256")
    req_payload = {
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": docusign_jwt
    }
    response = requests.post(
        BASE_URL + 'token', json=req_payload)
    if response:
        return response.json()['access_token']
    return None


''' Method to authenticate and return Api Client 
Api Client is required for any/ all docusign apis'''
def get_api_client():
    access_token = authenticate_docusign()
    if not access_token:
        return None
    api_client = ApiClient()
    api_client.host = REST_API_BASE_URL

    api_client.set_default_header(
        header_name="Authorization",
        header_value=f"Bearer {access_token}"
    )
    return api_client


''' Needs to allow application to be authenticated programmatically
for subsequent calls.
Hit below url for getting the authorization. This step has to be done only once.
# https://account-d.docusign.com/oauth/auth?response_type=code&scope=signature%20impersonation&client_id=<integration id>&redirect_uri=<callback url>
'''
def auth_callback(request):
    return HttpResponse("Authorized.")


'''
Below methods are required if application needs to be manually signed in everytime we need access
'''
# def get_access_code(request):
#     base_url=BASE_URL+"auth"
#     print(base_url)
#     print(request.build_absolute_uri(reverse('docusign:auth_login')))
#     auth_url="{0}?response_type=code&scope=signature&client_id={1}&redirect_uri={2}".format(base_url,
#         CLIENT_AUTH_ID,request.build_absolute_uri(reverse('docusign:auth_login')))
#     return HttpResponseRedirect(auth_url)


# def auth_login(request):
#     base_url = BASE_URL + "token"
#     auth_code_string="{0}:{1}".format(CLIENT_AUTH_ID,CLIENT_SECRET_KEY)
#     auth_token=base64.b64encode(auth_code_string.encode())
#     req_headers={"Authorization":"Basic {0}".format(auth_token.decode('utf-8'))}
#     post_data={'grant_type':'authorization_code','code':request.GET.get('code')}
#     r=requests.post(base_url,data=post_data,headers=req_headers)
#     response=r.json()
#     return HttpResponseRedirect("{0}?token={1}".format(reverse('docusign:get_signing_url'),response['access_token']))

'''
Method to embed signing in the app
Steps:
1. Authenticate Docusign and generate JWT 
2. Create Document object including document id and document to be signed
3. Create SignHere object to tell coordinates to sign
4. Create signer object and add it to envelope.
5. Once envelope is successfully created, save envelope id to appropriate model. 
This id is required to access envelope signing status and doc
'''
def embedded_signing_ceremony(request):
    signer_email = 'pulkit@gmail.com'
    signer_name = 'Pulkit Sachdeva'
    signer_user_id = '1' # to be retrieved from user model. Should be unique for each recipient
    doc_path = 'esign\Term_Of_Service.pdf'    
    # doc_path = settings.BASE_DIR + \
    #     static('demo_documents/Term_Of_Service.pdf')
    content_bytes = None
    with open(doc_path, "rb") as file:
        content_bytes = file.read()
    if not content_bytes:
        return Response(status=HTTP_400_BAD_REQUEST, data="No document available to be signed.")
    
    doc_b64 = base64.b64encode(content_bytes).decode("ascii")
    document = Document(
        document_base64=doc_b64,
        name='Example document',
        file_extension='pdf',
        # to be unique for every envelope. Since there's just one doc per envelope, id can be 1
        document_id=1,
    )
    
    signer = Signer(
        email=signer_email,
        name=signer_name,
        recipient_id=signer_user_id,
        routing_order="1",
        client_user_id=signer_user_id, # specifies this is an embedded request
        # Displays a form for conforming identity
        # require_id_lookup=True
    )

    sign_here = SignHere(
        document_id='1', 
        page_number='1', 
        recipient_id=signer_user_id, 
        tab_label='Sign Here',
        x_position='195', y_position='147')
    signer.tabs = Tabs(sign_here_tabs=[sign_here])
    
    envelope_definition = EnvelopeDefinition(
        email_subject="please sign the document to proceed with registration",
        documents=[document],
        recipients=Recipients(signers=[signer]),
        status="sent"
    )

    api_client = get_api_client()
    if not api_client:
        return Response(status=HTTP_400_BAD_REQUEST, data="API client not connected.")

    envelope_api = EnvelopesApi(api_client)
    results = envelope_api.create_envelope(
        account_id=ACCOUNT_ID, envelope_definition=envelope_definition)
    
    if not results:
        return Response(status=HTTP_400_BAD_REQUEST, data="Envelope not be created.")
    
    #Save envelope id in model
    envelope_id = results.envelope_id

    #Creates doc sign ui for signing
    recipient_view_request = RecipientViewRequest(
        authentication_method="None",
        client_user_id=signer_user_id,
        recipient_id=signer_user_id,
        return_url=request.build_absolute_uri(
            reverse('docusign:sign_completed')),
        user_name=signer_name,
        email=signer_email
    )
    
    results = envelope_api.create_recipient_view(
        ACCOUNT_ID, envelope_id, recipient_view_request=recipient_view_request)
    
    if not results:
        return Response(status=HTTP_400_BAD_REQUEST, data="Docusign UI not retrieved.")
    
    # Redirect to signing UI
    return HttpResponseRedirect(results.url)

'''
Method to take action once signing process is complete.
This method only tells a signing request has been completed.
It doesn't tell which request has been completed. 
Hence some polling logic has to be developed for querying the same
'''
def sign_complete(request):

    api_client = get_api_client()
    if not api_client:
        return Response(status=HTTP_400_BAD_REQUEST, data="API client not connected.")
    
    envelope_api = EnvelopesApi(api_client)
    # to be retrieved from model
    envelope_id = 'f2009d00-59b3-494b-b9b9-666a6cd5b814'
    results = envelope_api.get_envelope(
        account_id=ACCOUNT_ID, envelope_id=envelope_id, include=['documents'])

    sign_status = results.status
    if sign_status == 'completed':
        document_id = '1'
        # Save signed document to local
        #doc contains location
        doc = envelope_api.get_document(ACCOUNT_ID, document_id, envelope_id)
    else:
        # Save status to model
        pass
    return HttpResponse("sign in complete")
