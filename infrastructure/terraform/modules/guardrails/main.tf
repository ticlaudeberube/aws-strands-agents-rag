resource "aws_bedrock_guardrail" "rag_guardrail" {
  name                      = "${var.name_prefix}-guardrail"
  description               = "Perimeter safety, PII redaction, and grounding for Strands RAG (${var.stage})"
  blocked_input_messaging   = "I cannot process this request due to safety or topic restrictions."
  blocked_outputs_messaging = "I cannot provide a response that violates content or grounding policies."

  # Content & Prompt Injection Filtering (complements the in-code regex screen in src/agents/guardrails.py)
  content_policy_config {
    filters_config {
      input_strength  = "HIGH"
      output_strength = "NONE"
      type            = "PROMPT_ATTACK"
    }
    filters_config {
      input_strength  = "MEDIUM"
      output_strength = "MEDIUM"
      type            = "HATE"
    }
    filters_config {
      input_strength  = "MEDIUM"
      output_strength = "MEDIUM"
      type            = "MISCONDUCT"
    }
  }

  # PII Redaction & Blocking (US + Canadian identifiers)
  sensitive_information_policy_config {
    pii_entities_config {
      action = "ANONYMIZE"
      type   = "EMAIL"
    }
    pii_entities_config {
      action = "BLOCK"
      type   = "US_SOCIAL_SECURITY_NUMBER"
    }
    pii_entities_config {
      action = "BLOCK"
      type   = "CA_SOCIAL_INSURANCE_NUMBER"
    }
    pii_entities_config {
      action = "BLOCK"
      type   = "CA_HEALTH_NUMBER"
    }
  }

  # Contextual Grounding against OpenSearch retrieved chunks
  contextual_grounding_policy_config {
    filters_config {
      threshold = var.grounding_threshold
      type      = "GROUNDING"
    }
    filters_config {
      threshold = var.relevance_threshold
      type      = "RELEVANCE"
    }
  }

  tags = var.tags
}

# Immutable version snapshot of the DRAFT guardrail. A version never changes
# after creation, so the resource is replaced whenever the guardrail is updated;
# create_before_destroy keeps the Lambda pointed at a valid version during apply.
resource "aws_bedrock_guardrail_version" "rag_guardrail_v1" {
  guardrail_arn = aws_bedrock_guardrail.rag_guardrail.guardrail_arn
  description   = "Production guardrail version for ${var.stage}"

  lifecycle {
    create_before_destroy = true
    replace_triggered_by  = [aws_bedrock_guardrail.rag_guardrail]
  }
}
