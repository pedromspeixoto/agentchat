"""Usage statistics request/response schemas"""
from pydantic import BaseModel, ConfigDict, Field


class ChatUsageResponse(BaseModel):
    """Response model for chat usage statistics"""
    model_config = ConfigDict(from_attributes=True)
    
    id: str = Field(..., description="Usage record UUID")
    chat_id: str = Field(..., description="Chat session UUID")
    input_tokens: int = Field(..., ge=0, description="Input tokens used")
    output_tokens: int = Field(..., ge=0, description="Output tokens used")
    total_tokens: int = Field(..., ge=0, description="Total tokens used")
    cost_usd: float = Field(..., ge=0.0, description="Cost in USD")
    created_at: str = Field(..., description="ISO format creation timestamp")


class ChatUsageCreate(BaseModel):
    """Request model for creating usage statistics"""
    chat_id: str = Field(..., description="Chat session UUID")
    input_tokens: int = Field(0, ge=0, description="Input tokens used")
    output_tokens: int = Field(0, ge=0, description="Output tokens used")
    total_tokens: int = Field(0, ge=0, description="Total tokens used")
    cost_usd: float = Field(0.0, ge=0.0, description="Cost in USD")


class ChatContextResponse(BaseModel):
    """Response model for chat context (aggregated usage stats)"""
    chat_id: str
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    total_cost_usd: float
    context_window: int = 200000
