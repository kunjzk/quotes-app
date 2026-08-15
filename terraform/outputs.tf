output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.quotesapp.id
}

output "public_ip" {
  description = "Elastic IP address"
  value       = aws_eip.quotesapp.public_ip
}

output "app_url" {
  description = "Application URL"
  value       = "http://${aws_eip.quotesapp.public_ip}:8000"
}

output "ssh_command" {
  description = "SSH command to connect to the instance"
  value       = "ssh -i ~/.ssh/your-key.pem ubuntu@${aws_eip.quotesapp.public_ip}"
}

output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "subnet_id" {
  description = "Public subnet ID"
  value       = aws_subnet.public.id
}

output "security_group_id" {
  description = "Security group ID"
  value       = aws_security_group.quotesapp.id
}
