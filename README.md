# ZippMessage Post-Mortem
Note: Retired code from a bookmarking/link sharing app. The project is no longer live. Working on a complete rewrite at [zipp2](https://www.github.com/luthy2/zipp2). Try a live version at zipp2.herokuapp.com. <br/>

<a href="#overview">Overview</a>
<a href = "#details">Details</a>
<a href = "#screenshots">Screenshots</a>

## Overview <a name="overview">

### Conception
Zipp was conceived after noticing my friends and I were sending a lot of links in our group messages. I was unhappy that I could not easily find links if I wanted to revisit them, or forward them on to friends. I also noticed that many people used the @/mention feature on Instagram and Twitter to quickly share content with friends. I figured there should be an easy way to share links with friends, along with an easy way to save and organize them. Based on some initial research exploring bookmarking products like pocket, I felt that there was a product that should exist that didn't yet.

### Project
This was the first serious project I undertook, and my introduction to building web applications. At the start of this project, I had written some python, but I had never built something that could stand on its own. I encountered a lot of foundational ideas about building web applications up and down the stack, but some of my main areas of learning were:
  * WebApp frameworks
  * FrontEnd frameworks
  * Web Request Lifecycle and performance
  * REST/API and JSON
  * Relational and NoSQL databases
  * git

### Death
Ultimately, there were some strategic issues that ultimately led to the demise of the project, the main being relying on a vendor for a key feature. The link parsing and preview generation was handled by integrating with Embed.ly [www.emebly.com]. When embed.ly was acquired by Medium, the free tier of the API was removed and access now costs $99 a month. For a hobby project, this is not a price I am willing to pay. After assessing the options of writing my own link parser with similar features to embed.ly, or reintegrating another similar service, the task seemed thoroughly daunting and killed my momentum, and desire work on the project.

### Takeaway
Overall, I'm proud of what I was able to learn and build on my own. I went from barely being able to code, to being able to conceive an idea, implement it, and launch it. When the product was live, at its peak I had around 20 friends and family testing the product and giving me feedback. The code and design is certainly lacking some quality, but I made a conscious decision to prioritize quick and dirty feature implementations over following software development best practices, and visual polish. In the end, this lack of discipline contributed to the downfall of the project and serves as a valuable learning experience. So called "technical debt" can quickly compound and kill a project when it finally comes due. Likewise, vendor lock-in presents a significant risk particularly when the vendor is a key part of the product.


## Details <a name="details">

### Features and Technologies
#### Product Features
* One-to-one or one-to-many link sharing
* twitter login and friend lookup
* link preview
* emoji response
* quickshare bookmarklet
* article reader view
* bookmarking with tagging
* email notifications
* product analytics

#### Technologies
* web server written in python with flask
* front end written in javascript with Angular1.x
* hosted on Heroku
* asnyc operations with celery and memcached
* caching with celery and redis

## Screenshots <a name="screenshots">
![alt text](/app/static/img/richinbox.gif "Inbox with link previews")
Inbox with rich previews for different types of content.

![alt text](/app/static/img/quickshare.gif "quickshare bookmarklet")
quickly share links from the tab bar

![alt text](/app/static/img/messageactions.gif "send your reaction")
share your reaction on links shared with you

![alt text](/app/static/img/inbox.gif "Inbox with link previews")
inbox view
