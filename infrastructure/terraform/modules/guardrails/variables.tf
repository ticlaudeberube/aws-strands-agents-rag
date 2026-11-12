variable "name_prefix" {
  description = "Prefix used for Bedrock Guardrail names."
  type        = string
}

variable "stage" {
  description = "Deployment stage used in the Guardrail description."
  type        = string
}

variable "grounding_threshold" {
  description = "Minimum contextual grounding score before the guardrail intervenes."
  type        = number
  default     = 0.7

  validation {
    condition     = var.grounding_threshold >= 0 && var.grounding_threshold <= 1
    error_message = "grounding_threshold must be between 0 and 1."
  }
}

variable "relevance_threshold" {
  description = "Minimum query relevance score before the guardrail intervenes."
  type        = number
  default     = 0.7

  validation {
    condition     = var.relevance_threshold >= 0 && var.relevance_threshold <= 1
    error_message = "relevance_threshold must be between 0 and 1."
  }
}

variable "tags" {
  description = "Tags applied to the Guardrail resources."
  type        = map(string)
  default     = {}
}
