from django.db import models

class Team(models.Model):
    name = models.CharField(max_length=100)
    buzzer_pressed = models.BooleanField(default=False)
    color = models.CharField(max_length=50, default='#000000')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class BuzzerLog(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=50, choices=[('buzz', 'Buzz'), ('reset', 'Reset')])
    color = models.CharField(max_length=50, default='#000000')

    def __str__(self):
        return f"{self.action.capitalize()} - {self.team.name if self.team else 'Moderator'} at {self.timestamp}"

class GameSettings(models.Model):
    allow_self_reset = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Game Settings"
