# Observability child module (task 18.1).
#
# Provisions the serverless observability tier (Requirements 12.3, 12.4, 11.1):
#   - aws_cloudwatch_log_group per Lambda (/aws/lambda/<function_name>) with a
#     configurable retention (default 14 days).
#   - aws_cloudwatch_metric_alarm on the custom "errors/total" metric: alarms
#     when Sum(errors/total) > 10 over a single 5-minute (300s) window
#     (Req 12.3). The namespace is StrandsRAG/<stage> to EXACTLY match the
#     series emitted by the Lambda MetricsEmitter
#     (src/tools/cloudwatch_metrics.py -> metric_namespace()).
#   - Optional SNS topic wired as the alarm action.
#
# ---------------------------------------------------------------------------
# X-RAY (Requirement 12.4) — documentation note:
#   X-Ray ACTIVE tracing is already enabled on BOTH Lambda functions in the
#   compute module (tracing_config { mode = "Active" } on aws_lambda_function
#   "chat" and "indexing"). There is nothing to toggle here.
#
#   For traces to actually reach X-Ray, the Lambda execution role needs the
#   X-Ray write permissions xray:PutTraceSegments / xray:PutTelemetryRecords.
#   Those are granted by the AWS-managed policy AWSXRayDaemonWriteAccess. That
#   managed-policy attachment is added in the COMPUTE module (next to the
#   existing AWSLambdaVPCAccessExecutionRole attachment) rather than here,
#   because:
#     * The compute module owns the Lambda execution role.
#     * Property 31 forbids expanding the compute module's least-privilege
#       INLINE customer policy with extra actions. A MANAGED policy attachment
#       is exempt from that inline-policy scan, so attaching
#       AWSXRayDaemonWriteAccess satisfies Req 12.4 WITHOUT violating Property
#       31. The observability module intentionally does NOT touch the inline
#       policy.
# ---------------------------------------------------------------------------

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.79"
    }
  }
}

locals {
  # Namespace emitted by the handler: StrandsRAG/<stage> (STAGE env var). Allow
  # an explicit override but default to the stage-derived namespace so the
  # alarm watches the real metric stream.
  metric_namespace = var.metric_namespace_override != "" ? var.metric_namespace_override : "StrandsRAG/${var.stage}"

  # Metric name as emitted by MetricsEmitter.record_error() -> ERRORS_TOTAL.
  errors_total_metric_name = "errors/total"

  alarm_name = "${var.name_prefix}-errors-total"
}

# ---------------------------------------------------------------------------
# CloudWatch log groups — one per Lambda (Req 11.1 / observability).
#
# Pre-creating the log group lets us control retention (Lambda would otherwise
# auto-create it with "never expire"). The name MUST be /aws/lambda/<function>
# so the function writes into this managed group.
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "chat" {
  name              = "/aws/lambda/${var.chat_function_name}"
  retention_in_days = var.log_retention_in_days

  tags = merge(var.tags, { Name = "/aws/lambda/${var.chat_function_name}" })
}

resource "aws_cloudwatch_log_group" "indexing" {
  name              = "/aws/lambda/${var.indexing_function_name}"
  retention_in_days = var.log_retention_in_days

  tags = merge(var.tags, { Name = "/aws/lambda/${var.indexing_function_name}" })
}

# ---------------------------------------------------------------------------
# Optional SNS topic for alarm notifications. Subscriptions (email/Slack/etc.)
# are managed out-of-band; this just gives the alarm somewhere to publish.
# ---------------------------------------------------------------------------
resource "aws_sns_topic" "alarms" {
  count = var.enable_alarm_sns_topic ? 1 : 0

  name = "${var.name_prefix}-alarms"

  tags = merge(var.tags, { Name = "${var.name_prefix}-alarms" })
}

# ---------------------------------------------------------------------------
# errors/total alarm (Req 12.3): Sum(errors/total) > 10 in a 5-minute window.
#   period              = 300  (5 minutes)
#   evaluation_periods  = 1
#   threshold           = 10
#   comparison_operator = GreaterThanThreshold
#   statistic           = Sum
#   namespace           = StrandsRAG/<stage>  (matches the handler)
# treat_missing_data = notBreaching so quiet (no-error) windows stay OK.
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "errors_total" {
  alarm_name          = local.alarm_name
  alarm_description   = "Unhandled Lambda errors: Sum(${local.errors_total_metric_name}) > ${var.error_alarm_threshold} in 5 minutes (namespace ${local.metric_namespace}). Req 12.3."
  namespace           = local.metric_namespace
  metric_name         = local.errors_total_metric_name
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = var.error_alarm_threshold
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = var.enable_alarm_sns_topic ? [aws_sns_topic.alarms[0].arn] : []
  ok_actions    = var.enable_alarm_sns_topic ? [aws_sns_topic.alarms[0].arn] : []

  tags = merge(var.tags, { Name = local.alarm_name })
}
