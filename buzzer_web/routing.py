from django.urls import re_path
from channels.auth import AuthMiddlewareStack
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/buzzer/(?:(?P<team_id>\d+)/)?$', 
        AuthMiddlewareStack(consumers.BuzzerConsumer.as_asgi())
    ),
]
