from rest_framework import serializers


class OptimizeRouteSerializer(serializers.Serializer):
    start = serializers.CharField(
        required=True,
        allow_blank=False,
        error_messages={
            "required": "Start location is required.",
            "blank": "Start location cannot be empty.",
        },
    )
    destination = serializers.CharField(
        required=True,
        allow_blank=False,
        error_messages={
            "required": "Destination location is required.",
            "blank": "Destination location cannot be empty.",
        },
    )

    def validate(self, data):
        start = data.get("start", "").strip()
        destination = data.get("destination", "").strip()

        if start.upper() == destination.upper():
            raise serializers.ValidationError(
                "Start and destination locations cannot be the same."
            )

        return data
