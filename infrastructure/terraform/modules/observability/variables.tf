# Observability child module inputs (task 18.1).
#
# Wires CloudWatch log groups + the errors/total alarm to the compute-tier
# Lambda functions. The alarm namespace MUST match what the handler emits at
# runtime: the MetricsEmitter in src/tools/cloudwatch_metrics.py publishes to
# the namespace "StrandsRAG/{Stage}", where {Stage} is the STAGE env var
# (dev/staging/prod). We therefore take the raw `stage` here (NOT the
# "strands-rag-${stage}" name_prefix) so the alarm actually watches the series.

variable "name_prefix" {
  description = "Resource name prefix (e.g. strands-rag-dev). Used to name the alarm and SNS topic."
  type        = string
}

variable "stage" {
  description = "Deployment stage/environment name (dev, staging, prod). Used to build the CloudWatch metric namespace StrandsRAG/{stage}, matching what the Lambda MetricsEmitter emits (STAGE env var)."
  type        = string
}

variable "chat_function_name" {
  description = "Name of the chat handler Lambda function (compute module output). Drives the /aws/lambda/<name> log group."
  type        = string
}

variable "indexing_function_name" {
  description = "Name of the indexing handler Lambda function (compute module output). Drives the /aws/lambda/<name> log group."
  type        = string
}

variable "log_retention_in_days" {
  description = "Retention period (days) for both Lambda CloudWatch log groups."
  type        = number
  default     = 14

  validation {
    # Values accepted by CloudWatch Logs (0 = never expire).
    condition = contains(
      [0, 1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1096, 1827, 2192, 2557, 2922, 3288, 3653],
      var.log_retention_in_days
    )
    error_message = "log_retention_in_days must be a value supported by CloudWatch Logs (e.g. 1, 3, 7, 14, 30, 90, 365, ...)."
  }
}

variable "metric_namespace_override" {
  description = "Optional override for the CloudWatch metric namespace. Empty string (default) uses StrandsRAG/<stage>, matching the handler's MetricsEmitter."
  type        = string
  default     = ""
}

variable "error_alarm_threshold" {
  description = "errors/total count threshold that trips the alarm within a single 5-minute window (Req 12.3)."
  type        = number
  default     = 10
}

variable "enable_alarm_sns_topic" {
  description = "When true, create an SNS topic and wire it as the alarm action (and OK action). Kept optional/simple; subscriptions are managed out-of-band."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags applied to all resources created by this module."
  type        = map(string)
  default     = {}
}
