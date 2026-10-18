"""Authenticated DRF endpoint for data.gov.in-only chat."""

import logging

from asgiref.sync import async_to_sync
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from .llm_client import LLMServiceError
from .mcp_client import MCPServiceError
from .orchestrator import run_chat
from .serializers import ChatRequestSerializer

logger = logging.getLogger(__name__)


class ChatAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = ChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = serializer.validated_data["message"]

        try:
            result = async_to_sync(run_chat)(message)
        except (LLMServiceError, MCPServiceError):
            logger.exception("Data.gov.in chat service unavailable")
            return Response(
                {
                    "error": "The chat service is temporarily unavailable. Check the model and MCP server connections, then try again."
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception:
            logger.exception("Unexpected error in data.gov.in chat endpoint")
            return Response(
                {"error": "An unexpected chat error occurred."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(result, status=status.HTTP_200_OK)
