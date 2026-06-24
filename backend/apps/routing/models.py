import uuid
from django.db import models

class RouteCache(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    start_query = models.CharField(max_length=255)
    destination_query = models.CharField(max_length=255)
    start_lat = models.FloatField()
    start_lon = models.FloatField()
    dest_lat = models.FloatField()
    dest_lon = models.FloatField()
    distance_miles = models.FloatField()
    estimated_duration = models.FloatField()
    route_geometry = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'route_cache'

    def __str__(self):
        return f"{self.start_query} to {self.destination_query} ({self.distance_miles} miles)"
