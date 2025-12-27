"""Optimized FastAPI endpoint with async support."""
from fastapi import FastAPI
from pydantic import BaseModel, Field
from ai_parser_optimized import smart_parse_async, ParseResult

class ParseRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    force_ai: bool = False
    text_alternatives: list[str] | None = Field(None, max_length=5)

@app.post("/ai/parse", response_model=ParseResult)
async def parse_voice_input(request: ParseRequest) -> ParseResult:
    """Async voice parsing with alternative handling."""
    result = await smart_parse_async(request.text, request.force_ai)
    
    # Try alternatives if main result is weak
    if request.text_alternatives and (not result['items'] or result['confidence'] == 'low'):
        for alt in request.text_alternatives[1:]:
            alt_result = await smart_parse_async(alt, request.force_ai)
            if alt_result['items'] and alt_result['confidence'] == 'high':
                alt_result['used_alternative'] = alt
                return alt_result
    
    return result
