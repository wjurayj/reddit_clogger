# Your anonymous online conversations are mostly with bots!

This project provides a skeleton illustrating how a user can periodically filter through conversations and comments on Reddit, and upload responses to individual comments based on a set of rules & targets. 

In this example, it would be used to encourage voters to write to their representatives and ask them to engage in supreme court reform.
Adjustments to the THREAD_INTEREST_PROMPT, COMMENT_INTEREST_PROMPT, and COMMENT_REPLY_PROMPT can be used to adjust the publishing strategy.

NOTE: DO NOT DEPLOY THIS SYSTEM WITHOUT UPDATING `openai.api_base` TO REFLECT YOUR LOCALLY HOSTED INSTANCE. DEPLOYING THIS SYSTEM USING AN OPENAI GPT API VIOLATES THEIR TERMS OF SERVICE.

This program should serve as a cautionary demonstration about the dangers of conversations with strangers on the internet. Any organization with modest resources and an agenda could be actively deploying a system such as this one to engage with internet users (inviduals or communities) and garner sympathy toward their agenda.

