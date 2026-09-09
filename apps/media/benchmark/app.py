"""Application-specific benchmark entrypoint."""
import os
from vic_apps.server import create_app as shared_app

def create_app():
    os.environ['VIC_APP_MODULES']='media'
    return shared_app()
