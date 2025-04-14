# Use an official Python runtime as the base image
FROM python:3.11.7-slim

RUN rm -rf /netflowips
# Install system packages
RUN apt-get update && apt-get install -y \
    git \
    supervisor \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Clone the repository
RUN git clone https://github.com/mayberryjp/netflowips.git /netflowips

# Set the working directory
WORKDIR /netflowips

RUN pip install schedule requests

# Expose the port
EXPOSE 2055

# Run the app
CMD ["/usr/bin/supervisord", "-n", "-c", "/netflowips/super.conf"]