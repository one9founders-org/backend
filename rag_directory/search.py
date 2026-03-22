from django.db.models import Q
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from rag_directory.models import RagTool
from rag_directory.serializers import RagToolListSerializer
from research_papers.models import Paper
from research_papers.serializers import PaperListSerializer


@api_view(["GET"])
@permission_classes([AllowAny])
def global_search(request):
    query = request.query_params.get("q", "").strip()
    search_types = request.query_params.get("type", "rag,papers").split(",")

    if not query or len(query) < 2:
        return Response({"rag": [], "papers": []})

    results = {"rag": [], "papers": []}

    if "rag" in search_types:
        rag_tools = RagTool.objects.filter(
            Q(name__icontains=query) | Q(description__icontains=query),
            status="active",
        )[:10]
        results["rag"] = RagToolListSerializer(rag_tools, many=True).data

    if "papers" in search_types:
        papers = Paper.objects.filter(
            Q(title__icontains=query) | Q(abstract__icontains=query)
        )[:10]
        results["papers"] = PaperListSerializer(papers, many=True).data

    return Response(results)
