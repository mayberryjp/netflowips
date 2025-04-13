# Use an official Python runtime as the base image
ARG CACHEBUST=1 
FROM python:3.11.7

# Set the working directory
WORKDIR /netflowips-v0.0.1

# Copy the requirements file
#COPY requirements.txt .
#RUN cd /
RUN git clone https://github.com/mayberryjp/netflowips.git .
# Create a virtual environment and install the dependencies
RUN python -m venv venv
RUN venv/bin/pip install --upgrade pip

# Copy the app files
#COPY myapp/ .

# Expose the port
#EXPOSE 5102

# Run the app
CMD ["venv/bin/python","-u", "collector.py"]