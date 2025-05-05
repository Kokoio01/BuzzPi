import json
import logging
from typing import Optional, Dict, Any

from channels.db import database_sync_to_async
from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.apps import apps
from .models import Team

from .exceptions import BuzzerException

logger = logging.getLogger(__name__)


class BuzzerConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for handling real-time buzzer interactions between teams.

    Attributes:
        room_group_name (str): Name of the WebSocket group for broadcasting
        team_id (Optional[int]): ID of the team associated with this connection
        active_buzzers (Dict): Class variable tracking active buzzer states
    """

    active_buzzers: Dict[int, bool] = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.room_group_name = "buzzer_group"
        self.team_id: Optional[int] = None

    async def connect(self):
        try:
            team_id_str = self.scope['url_route']['kwargs'].get('team_id')
            if team_id_str:
                self.team_id = int(team_id_str)
                if not await self.get_team(self.team_id):
                    await self.close(code=4000)
                    return
            else:
                self.team_id = None

            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            await self.accept()
            await self.send_initial_state()

        except (ValueError, KeyError) as e:
            logger.error(f"Connection error: {str(e)}")
            await self.close(code=4001)

    async def disconnect(self, close_code):
        """Clean up on disconnect: remove from group and clear buzzer state."""
        try:
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

        except Exception as e:
            logger.error(f"Disconnect error: {str(e)}")

    async def receive(self, text_data):
        """Handle incoming WebSocket messages."""
        try:
            data = json.loads(text_data)
            
            admin_actions = ['add_team', 'remove_team', 'clear_teams', 'set_self_reset', 'reset_admin']
            if data.get('type') in admin_actions:
                if not (self.scope.get('user') and self.scope['user'].is_authenticated):
                    await self.send_error("Authentication required")
                    return

                if data['type'] == 'add_team':
                    await self.handle_add_team(data['name'], data['color'])
                elif data['type'] == 'remove_team':
                    await self.handle_remove_team(data['team_id'])
                elif data['type'] == 'clear_teams':
                    await self.handle_clear_teams()
                elif data['type'] == 'set_self_reset':
                    await self.handle_set_self_reset(data['enabled'])
                elif data['type'] == 'reset_admin':
                    await self.handle_reset(True) # Override self-reset
                return

            if data.get('type') == 'buzz':
                await self.handle_buzz(data['team_id'], data.get('color', '#000000'))
            elif data.get('type') == 'reset':
                await self.handle_reset(False)
            elif data.get('type') == 'get_state':
                await self.send_initial_state()

        except Exception as e:
            await self.send_error(str(e))

    async def handle_add_team(self, name, color):
        team = await self.add_team(name, color)
        await self.broadcast_and_send()
        await self.send(text_data=json.dumps({
            'type': 'team_update',
            'update_type': 'added',
            'team': {
                'id': team.id,
                'name': team.name,
                'color': team.color
            }
        }))

    async def handle_remove_team(self, team_id):
        await self.remove_team(team_id)
        await self.broadcast_and_send()
        await self.send(text_data=json.dumps({
            'type': 'team_update',
            'update_type': 'removed',
            'team_id': team_id
        }))

    async def handle_clear_teams(self):
        await self.clear_teams()
        await self.broadcast_and_send()
        await self.send(text_data=json.dumps({
            'type': 'team_update',
            'update_type': 'cleared'
        }))

    async def handle_set_self_reset(self, enabled):
        setting = await self.set_self_reset(enabled)
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'settings_update',
                'settings': {'allow_self_reset': setting}
            }
        )

    async def handle_buzz(self, team_id: int, color: str):
        if await self.any_buzzer_pressed():
            await self.send_error("Another team has already buzzed. Wait for reset.")
            return

        await self.update_buzzer_state(team_id, True)
        await self.log_buzzer_event(team_id, color, action='buzz')

        team = await self.get_team(team_id)
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'buzzer_type',
                'buzz_type': 'buzz',
                'team_id': team_id,
                'team_name': team.name if team else None,
                'color': team.color if team else None,
                'timestamp': self.get_timestamp() * 1000  # Convert to milliseconds
            }
        )

    @database_sync_to_async
    def is_self_reset_allowed(self):
        """Check if teams are allowed to reset their own buzzers"""
        GameSettings = apps.get_model('buzzer_web', 'GameSettings')
        settings = GameSettings.objects.first()
        return settings.allow_self_reset if settings else True

    async def handle_reset(self, force: bool):
        if not await self.is_self_reset_allowed() and not force:
            await self.send_error("Teams are not allowed to reset their own buzzers")
            return
            
        await self.reset_all_buzzer_states()

        await self.log_buzzer_event(None, '#000000', action='reset')

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'buzzer_type',
                'buzz_type': 'reset',
                'team_name': None,
                'timestamp': None
            }
        )

    @database_sync_to_async
    def log_buzzer_event(self, team_id: Optional[int], color: str, action: str):
        """Log a buzzer action (buzz or reset) in the database."""
        BuzzerLog = apps.get_model('buzzer_web', 'BuzzerLog')
        team = Team.objects.get(id=team_id) if team_id else None
        BuzzerLog.objects.create(team=team, color=color, action=action)

    @database_sync_to_async
    def reset_all_buzzer_states(self):
        """Reset all buzzer states in the database."""
        Team.objects.update(buzzer_pressed=False)

    async def send_error(self, message: str):
        """Send error message to client."""
        await self.send(text_data=json.dumps({
            'error': message
        }))

    @database_sync_to_async
    def get_buzzer_states(self):
        """Get all current buzzer states from database."""
        return {team.id: team.buzzer_pressed for team in Team.objects.all()}

    @database_sync_to_async
    def get_team(self, team_id: int) -> Optional[Any]:
        """Fetch team from database."""
        try:
            return Team.objects.get(id=team_id)
        except Team.DoesNotExist:
            return None

    @database_sync_to_async
    def update_buzzer_state(self, team_id: int, state: bool):
        """Update team's buzzer state in database."""
        try:
            with transaction.atomic():
                team = Team.objects.select_for_update().get(id=team_id)
                team.buzzer_pressed = state
                team.save(update_fields=['buzzer_pressed'])
                return team
        except Team.DoesNotExist:
            print(f"Team {team_id} not found")
            raise BuzzerException(f"Team {team_id} not found")
        except Exception as e:
            print(f"Error updating buzzer state: {str(e)}")
            raise

    @database_sync_to_async
    def any_buzzer_pressed(self):
        try:
            pressed_teams = Team.objects.filter(Q(buzzer_pressed=True))
            result = pressed_teams.exists()
            return result
        except Exception as e:
            print(f"Error in any_buzzer_pressed: {str(e)}")
            # Re-raise to maintain error handling
            raise

    @staticmethod
    def get_timestamp() -> float:
        """Get current timestamp for buzz ordering."""
        from time import time
        return time()

    @database_sync_to_async
    def get_all_team_states(self):
        """Get the current state of all teams including their details."""
        return {
            team.id: {
                'buzzer_pressed': team.buzzer_pressed,
                'name': team.name,
                'color': team.color
            }
            for team in Team.objects.all()
        }

    @database_sync_to_async
    def get_current_buzzer_status(self):
        """Get the currently active team if any."""
        BuzzerLog = apps.get_model('buzzer_web', 'BuzzerLog')
        active_team = Team.objects.filter(buzzer_pressed=True).first()
        if active_team:
            return {
                'team_name': active_team.name,
                'color': active_team.color,
                'timestamp': BuzzerLog.objects.filter(
                    team=active_team, 
                    action='buzz'
                ).latest('timestamp').timestamp.timestamp() * 1000
            }
        return None

    @database_sync_to_async
    def get_settings(self):
        """Get current game settings"""
        GameSettings = apps.get_model('buzzer_web', 'GameSettings')
        settings = GameSettings.objects.first()
        if not settings:
            settings = GameSettings.objects.create()
        return {'allow_self_reset': settings.allow_self_reset}

    async def send_initial_state(self):
        """Send the current state of all buzzers to the client."""
        active_buzzers = await self.get_all_team_states()
        current_status = await self.get_current_buzzer_status()
        teams = await sync_to_async(list)(Team.objects.all().values('id', 'name', 'color'))
        settings = await self.get_settings()
        
        await self.send(text_data=json.dumps({
            'type': 'initial_state',
            'active_buzzers': active_buzzers,
            'current_status': current_status,
            'teams': teams,
            'settings': settings
        }))

    @database_sync_to_async
    def add_team(self, name, color):
        team = Team.objects.create(name=name, color=color)
        return team

    @database_sync_to_async
    def remove_team(self, team_id):
        Team.objects.filter(id=team_id).delete()

    @database_sync_to_async
    def clear_teams(self):
        Team.objects.all().delete()

    @database_sync_to_async
    def set_self_reset(self, enabled):
        if not (self.scope.get('user') and self.scope['user'].is_authenticated):
            raise BuzzerException("Authentication required to change settings")
        GameSettings = apps.get_model('buzzer_web', 'GameSettings')
        settings, _ = GameSettings.objects.get_or_create(id=1)
        settings.allow_self_reset = enabled
        settings.save()
        return settings.allow_self_reset  # Return the actual saved value

    @database_sync_to_async
    def broadcast_team_update(self):
        """Send updated team list to all clients"""
        teams = list(Team.objects.all().values('id', 'name', 'color'))
        return teams  # Return the teams instead of awaiting channel_layer

    async def broadcast_and_send(self):
        """Helper method to broadcast team updates"""
        teams = await self.broadcast_team_update()
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'team_list_update',
                'teams': teams
            }
        )

    async def team_list_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'team_list',
            'teams': event['teams']
        }))

    async def settings_update(self, event):
        """Handle settings update broadcasts"""
        await self.send(text_data=json.dumps({
            'type': 'settings_update',
            'settings': event['settings']
        }))

    async def buzzer_type(self, event):
        """Handle buzzer type events and forward to clients."""
        await self.send(text_data=json.dumps({
            'type': 'buzzer_type',
            'action': event.get('buzz_type'),
            'team_id': event.get('team_id'),
            'team_name': event.get('team_name'),
            'color': event.get('color'),
            'timestamp': event.get('timestamp')
        }))