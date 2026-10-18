from rest_framework import serializers


class ChatRequestSerializer(serializers.Serializer):
    message = serializers.CharField(
        max_length=4000,
        trim_whitespace=True,
        allow_blank=False,
        help_text="A request to find, retrieve, inspect, or analyze data.gov.in datasets.",
    )
