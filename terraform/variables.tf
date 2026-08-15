variable "aws_region" {
  description = "AWS region to deploy to"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "quotesapp"
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.small"
}

variable "ssh_allowed_ips" {
  description = "CIDR blocks allowed to SSH into the instance"
  type        = list(string)
  default     = ["0.0.0.0/0"] # Change this to your IP for better security
}

variable "ssh_public_key" {
  description = "SSH public key for EC2 access"
  type        = string
}

variable "postgres_password" {
  description = "PostgreSQL password"
  type        = string
  sensitive   = true
}

variable "django_secret_key" {
  description = "Django secret key"
  type        = string
  sensitive   = true
}

variable "ses_smtp_username" {
  description = "AWS SES SMTP username"
  type        = string
  sensitive   = true
  default     = ""
}

variable "ses_smtp_password" {
  description = "AWS SES SMTP password"
  type        = string
  sensitive   = true
  default     = ""
}

variable "ses_smtp_host" {
  description = "AWS SES SMTP host"
  type        = string
  default     = "email-smtp.us-east-1.amazonaws.com"
}

variable "ses_smtp_port" {
  description = "AWS SES SMTP port"
  type        = number
  default     = 587
}

variable "default_from_email" {
  description = "Default FROM email address (must be verified in SES)"
  type        = string
}
