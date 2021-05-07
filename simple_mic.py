import asyncio
# This example uses the sounddevice library to get an audio stream from the
# microphone. It's not a dependency of the project but can be installed with
# `pip install sounddevice`.
import sounddevice
from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from amazon_transcribe.model import TranscriptEvent
import boto3
from dotenv import load_dotenv
import os

"""
Here's an example of a custom event handler you can extend to
process the returned transcription results as needed. This
handler will simply print the text out to your interpreter.
"""

# Full list for AWS transcribe
# https://docs.aws.amazon.com/transcribe/latest/dg/what-is-transcribe.html
# Full list for AWS translate
# https://docs.aws.amazon.com/translate/latest/dg/what-is.html#what-is-languages


def set_config():
    
    #loads the .env file with our credentials
    load_dotenv() 

    SourceLanguage = os.getenv('SOURCE_LAN')
    TargetLanguage = os.getenv('TARGET_LAN')

    transcribe_source_lan = "en" if "en" in SourceLanguage else SourceLanguage

    config = {
        "transcribe":{"language_code":SourceLanguage},
        "translate":{
            "SourceLanguageCode" : transcribe_source_lan,
            "TargetLanguageCode" : TargetLanguage
            }
        }
    return config

async def text_translate(text):
    translate = boto3.client(service_name='translate', region_name='eu-west-2', use_ssl=True)

    result = translate.translate_text(
        Text = text, 
        SourceLanguageCode = set_config()["translate"]["SourceLanguageCode"], 
        TargetLanguageCode = set_config()["translate"]["TargetLanguageCode"])

    print('Translation: ' + result.get('TranslatedText'))

class MyEventHandler(TranscriptResultStreamHandler):
    async def handle_transcript_event(self, transcript_event: TranscriptEvent):
        # This handler can be implemented to handle transcriptions as needed.
        # Here's an example to get started.
        results = transcript_event.transcript.results

        for result in results:
            for alt in result.alternatives:
                if result.is_partial == False: 
                    print("Original: " + alt.transcript)
                    await text_translate(alt.transcript)


async def mic_stream():
    # This function wraps the raw input stream from the microphone forwarding
    # the blocks to an asyncio.Queue.
    loop = asyncio.get_event_loop()
    input_queue = asyncio.Queue()

    def callback(indata, frame_count, time_info, status):
        loop.call_soon_threadsafe(input_queue.put_nowait, (bytes(indata), status))

    # Be sure to use the correct parameters for the audio stream that matches
    # the audio formats described for the source language you'll be using:
    # https://docs.aws.amazon.com/transcribe/latest/dg/streaming.html
    stream = sounddevice.RawInputStream(
        channels=1,
        samplerate=16000,
        callback=callback,
        blocksize=1024 * 2,
        dtype="int16",
    )
    # Initiate the audio stream and asynchronously yield the audio chunks
    # as they become available.
    with stream:
        while True:
            indata, status = await input_queue.get()
            yield indata, status


async def write_chunks(stream):
    # This connects the raw audio chunks generator coming from the microphone
    # and passes them along to the transcription stream.
    async for chunk, status in mic_stream():
        await stream.input_stream.send_audio_event(audio_chunk=chunk)
    await stream.input_stream.end_stream()


async def basic_transcribe():
    # Setup up our client with our chosen AWS region
    client = TranscribeStreamingClient(region="us-west-2")

    # Start transcription to generate our async stream
    stream = await client.start_stream_transcription(
        language_code = set_config()["transcribe"]["language_code"],
        media_sample_rate_hz = 16000,
        media_encoding = "pcm",
    )

    # Instantiate our handler and start processing events
    handler = MyEventHandler(stream.output_stream)
    await asyncio.gather(write_chunks(stream), handler.handle_events())


loop = asyncio.get_event_loop()
loop.run_until_complete(basic_transcribe())
loop.close()