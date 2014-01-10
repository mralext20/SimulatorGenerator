#!/usr/bin/env python

import sys
import os
import ConfigParser
import requests
from xml.dom import minidom
import json
import random
import mimetypes
import datetime
import subprocess
import re
import traceback

import twitter
import titlecase

creds = ConfigParser.ConfigParser()
twitterApi = None

def setup():
    global creds
    global twitterApi

    random.seed()

    creds.read("credentials.ini")

    consumer_key = creds.get("twitter", "consumerkey")
    consumer_secret = creds.get("twitter", "consumersecret")
    access_token = creds.get("twitter", "accesstoken")
    access_token_secret = creds.get("twitter", "accesstokensecret")
    twitterApi = twitter.Api(consumer_key, consumer_secret, access_token, access_token_secret)

def getJobTitle():
    # TODO: store off the category, don't repeat job titles, rotate categories
    #   http://api.careerbuilder.com/CategoryCodes.aspx

    cb_apiKey = creds.get("careerbuilder", "apikey")
    js_params = {
        "DeveloperKey" : cb_apiKey,
        "HostSite" : "US",
        "OrderBy" : "Date",
    }
    cb_URL = "http://api.careerbuilder.com/v1/jobsearch?"

    response = requests.get(cb_URL, params=js_params)
    dom = minidom.parseString(response.content)
    # dom = minidom.parse(open("sample_jobsearch.xml"))
    jobs = []
    for node in dom.getElementsByTagName("JobTitle"):
        jobs.append(node.firstChild.nodeValue)

    job = random.choice(jobs)
    job = job.replace("'", "\\'").replace('"', '\\"')
    return job

def getImageFor(searchTerm):
    is_params = {
        "v" : "1.0", 
        "q" : searchTerm, 
        "imgType" : "photo",
        "imgsz" : "small|medium|large|xlarge|xxlarge|huge"
    }
    headers = {"Referer" : "https://twitter.com/SimGenerator"}
    is_URL = "https://ajax.googleapis.com/ajax/services/search/images"

    imageResults = requests.get(is_URL, params=is_params).json()
    # imageResults = json.load(open("sample_imagesearch.json"))
    if (imageResults == None or 'responseData' not in imageResults or imageResults['responseData'] == None):
        sys.stderr.write("No response data in image search for %s. JSON:\n%s\n" % (searchTerm, imageResults))
        return
    imageData = []
    for image in imageResults['responseData']['results']:
        imageData.append(
            {
                "url" : image['url'], 
                "h" : int(image['height']), 
                "w" : int(image['width']), 
                "size" : int(image['width']) * int(image['height'])
            }
        )
    imageData.sort(reverse=True, key=lambda img: img['size'])

    mimetypes.init()
    for img in imageData:
        try:
            r = requests.head(img['url'])
            if not r.ok:
                # can't download for whatever reason
                continue
        except:
            # requests library puked
            continue

        try:
            extension = mimetypes.guess_extension(r.headers['Content-Type'])
        except KeyError, e:
            sys.stderr.write("Couldn't find content-type header: %s" % str(r.headers))
            extension = ""
        if (extension == ".jpe") : extension = ".jpg"

        localFileName = "tmp/base_image-%s%s" % (datetime.datetime.now().strftime("%Y-%m-%d-%H%M.%f"), extension)
        baseFile = open(localFileName, 'wb')
        imgResponse = requests.get(img['url'])
        baseFile.write(imgResponse.content)
        baseFile.close()

        # check our work
        cmdLine = ['identify', '-format', '%wx%h', localFileName]
        dimensionString = subprocess.Popen(cmdLine, stdout=subprocess.PIPE).communicate()[0]
        dimensions = dimensionString.split("x")
        if (int(dimensions[0]) == img['w'] and int(dimensions[1]) == img['h']):
            return localFileName

def cap(value, maxVal):
    if (value < maxVal):
        return value
    else:
        return maxVal

def wpl(totalwords, current=None):
    if (current == None):
        current = []

    if (totalwords == 0):
        return current
    if (totalwords == 1):
        current.append(1)
        return current
    if (totalwords % 3 == 0):
        return current + [3]*(totalwords/3)
    current.append(2)
    return wpl(totalwords-2, current)

def createBoxArt(jobTitle, localImgFile, year):
    grav = random.choice(("NorthWest", "NorthEast", "SouthWest", "SouthEast"))
    if grav[-4:] == "West":
        align = "West"
    else:
        align = "East"

    wordlist = jobTitle.split()
    wordsPerLine = wpl(len(wordlist))
    jobTitle = ""
    indent = " "
    for wordCount in wordsPerLine:
        while wordCount > 0:
            jobTitle += wordlist.pop(0) + " "
            wordCount -= 1
        jobTitle += "\n"
        if (align == "West"):
            jobTitle += indent
            indent += " "

    # newlines to deal with the font overruning its rendering bounds; 
    #   we trim the canvas in imagemagick anyway
    jobTitle = "\n%sSimulator %i\n" % (jobTitle, year)

    cmdLine = ['identify', '-format', '%wx%h', localImgFile]
    try:
        dimensionString = subprocess.Popen(cmdLine, stdout=subprocess.PIPE).communicate()[0]
    except TypeError, e:
        sys.stderr.write("Couldn't get dimensions for %s\n" % localImgFile)
        return
    dimensions = map(int, dimensionString.split("x"))

    if (dimensions[0] > dimensions[1]):
        widthMultiplier = 0.65
    else:
        widthMultiplier = 0.95

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M.%f")
    offset = "+%i+%i" % (cap(dimensions[0] * .05, 20), cap(dimensions[1] * .05, 20))
    command = [
        "convert",
        "-background", "none",
        "-fill", "white",
        "-stroke", "gray",
        "-strokewidth", "3",
        "-kerning", "-5",
        "-font", "./helvetica-ultra-compressed.ttf",
        "-pointsize", "300",
        "-gravity", align,
        "-interline-spacing", "75",
        ("label:%s" % jobTitle).encode("utf8"),
        "-shear", "10x0",
        "-trim",
        "-resize", "%ix%i" % (dimensions[0] * widthMultiplier, dimensions[1] * .95),
        localImgFile, "+swap",
        "-gravity", grav,
        "-geometry", offset,
        "-composite",
        "-resize", "1500x1500>",
        "output-%s.png" % timestamp
    ]

    subprocess.call(command)
    os.rename(localImgFile, "archive/%s" % os.path.basename(localImgFile))
    return "output-%s.png" % timestamp

def tweet(job, year, artFile, respondingTo=None):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M.%f")
    title = "%s Simulator %i" % (job, year)

    userName = None
    requestId = None
    if (respondingTo != None):
        userName = respondingTo[0]
        requestId = respondingTo[1]

    if (artFile != None and os.path.exists(artFile)):
        if (userName != None):
            title = "@%s %s" % (userName, title)
        twitterApi.PostMedia(title, artFile, in_reply_to_status_id=requestId)

        os.rename(artFile, "archive/image-%s.png" % timestamp)
        archFile = open("archive/text-%s.txt" % timestamp, "w")
        archFile.write(title.encode('utf8'))
        archFile.close()
    else:
        # don't tweet; something's wrong. 
        print("FAILURE: %s" % title.encode("utf8"))
        archFile = open("archive/failed-%s.txt" % timestamp, "w")
        archFile.write(title.encode('utf8'))
        archFile.close()

def checkTwitterLimits():
    rateLimitData = twitterApi.GetRateLimitStatus()

    rateLimitCallsLeft = rateLimitData['resources']['application']['/application/rate_limit_status']['remaining']
    rateLimitReset = rateLimitData['resources']['application']['/application/rate_limit_status']['reset']
    mentionsCallsLeft = rateLimitData['resources']['statuses']['/statuses/mentions_timeline']['remaining']
    mentionsReset = rateLimitData['resources']['statuses']['/statuses/mentions_timeline']['reset']

    print mentionsCallsLeft, "mentions calls left."

def randomJobTweet():
    job = getJobTitle()
    image = getImageFor(job)
    year = random.randint(2007, datetime.date.today().year)
    art = createBoxArt(job, image, year)
    tweet(job, year, art)

def respondToRequests():
    lastReply = 0
    lastReplyFile = "last_replied_to.txt"
    if (os.path.exists(lastReplyFile)):
        with open(lastReplyFile, "r") as f:
            lastReply = int(f.read())

    badwordsFile = open("badwords.json", "r")
    badwordsData = json.load(badwordsFile)
    badwordsFile.close()
    badwords = badwordsData['badwords']

    requestRegex = re.compile('make one about ([^,\.\n@]*)', re.IGNORECASE)

    mentions = twitterApi.GetMentions(since_id=lastReply)
    mentions.reverse()
    for status in mentions:
        result = requestRegex.search(status.text)
        if (result):
            job = result.groups()[0]
            # because regex is annoying
            if (job.lower().startswith("a ")):
                job = job[2:]
            elif (job.lower().startswith("an ")):
                job = job[3:]
            job = titlecase.titlecase(job)

            earlyOut = False
            for word in job.split():
                if word in badwords:
                    earlyOut = True
            if earlyOut: continue

            try:
                image = getImageFor(job)
                year = random.randint(2007, datetime.date.today().year)
                art = createBoxArt(job, image, year)
                tweet( job, year, art, (status.user.screen_name, str(status.id)) )
            except Exception, e:
                sys.stderr.write("Couldn't respond to request: %s\n" % status.text.encode("utf8"))
                traceback.print_exc(file=sys.stderr)
            finally:
                lastReply = status.id

    with open(lastReplyFile, "w") as f:
        f.write(str(lastReply))


if __name__ == '__main__':
    base = os.path.dirname(os.path.abspath( __file__ ))
    os.chdir(base)
    
    setup()

    if (len(sys.argv) > 1 and sys.argv[1] == "check"):
        respondToRequests()
    else:
        randomJobTweet()

