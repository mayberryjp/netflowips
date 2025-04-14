# Use an official Python runtime as the base image
ARG CACHEBUST=1 
FROM python:3.11.7

# Set the working directory
WORKDIR /netflowips-v0.0.7

RUN apt-get update && apt-get install -y supervisor && mkdir -p /var/log/supervisor

RUN git clone https://github.com/mayberryjp/netflowips.git .

RUN python -m venv venv
RUN venv/bin/pip install --upgrade pip
RUN venv/bin/pip install schedule
RUN venv/bin/pip install requests

# Install supervisord


# Copy your supervisor configuration
#COPY super.conf /etc/supervisor/supervisord.conf

# Copy the requirements file
#COPY requirements.txt .
#RUN cd /

# Create a virtual environment and install the dependencies

# Copy the app files
#COPY myapp/ .

# Expose the port
#EXPOSE 5102

# Run the app
#CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]
CMD ["/usr/bin/supervisord", "-n", "-c", "super.conf"]

#CMD ["venv/bin/python","-u", "collector.py"]