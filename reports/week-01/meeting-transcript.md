# Kickoff meeting transcript

**Date:** 2026-10-02
**Participants:** azamatbayramov, Customer, Guest (a member of another course team working on the same project)

Cleaned from the meeting's automatic English transcript.
Backchannel remarks ("mm-hmm", "okay") are omitted.
Names of people mentioned in the conversation and a team member's employer are replaced with `[redacted]`.

[00:00:04] azamatbayramov: Will we have a recording of this meeting?
[00:00:10] Customer: Yes, I started the transcript, so let's start the recording too.
[00:00:35] Customer: Do you want an actual recording or transcripts?
[00:00:40] azamatbayramov: For us, a recording and a transcript are fine.
[00:00:51] Customer: We now have both the transcript and the recording, so we should be good.
[00:00:51] Customer: In Zoom I can also send you a link.
[00:01:00] Customer: So you are planning to work on the LLM gateway.
[00:01:00] Customer: Did you do any research on the topic?
[00:01:19] Guest: Yes, my team researched alternatives and even developed our vision of the product.
[00:01:32] Customer: I would like to start with your vision, then I'll tell you what I had in mind, and we'll try to synchronize.
[00:01:46] Guest: First I want to ask some questions about the project, because we need to understand it.
[00:01:54] Customer: One of the teams is "cinema", and you are representing it, right?
[00:02:04] Guest: Yes, I am.
[00:02:06] Customer: [inaudible], right?
[00:02:08] azamatbayramov: Our team is Team 7, and our team name is iTeam7.
[00:02:15] Customer: I'll create that in the Telegram channel.
[00:02:15] Customer: Go ahead with your questions.
[00:02:31] Guest: The first description had only one use case: filtering data such as personal data.
[00:02:31] Guest: Many existing solutions already deal with that problem.
[00:02:54] Customer: I know.
[00:02:54] Customer: I thought I included other things; it's not just filtering data.
[00:03:02] Customer: I know there's LiteLLM and similar products.
[00:03:13] Customer: For example, you want access control, where different people have access to different LLMs.
[00:03:22] Customer: Another one is tracking token usage.
[00:03:36] Customer: A lot of this already exists, and you can combine a bunch of products to get it.
[00:03:46] Customer: One use case: you have a codebase that should not go into any LLM, you fingerprint that codebase, and as soon as you detect it...
[00:04:00] Customer: Just a second, sorry.
[00:05:03] Customer: So one use case is a fingerprinted codebase that is very important to your company and should not touch an LLM.
[00:05:18] Customer: Some code is fine, and some you want to detect.
[00:05:29] Customer: The problem is that existing solutions force you into how to fingerprint it.
[00:05:34] Customer: For this project, the whole idea is to build a modular system where you can, for example, ask an LLM to build the modules you need on top of it.
[00:05:52] Customer: Lots of companies have their own logging system: logging tokens, logging what was asked.
[00:06:07] Customer: They have different requirements for what needs to be logged and how.
[00:06:07] Customer: So you end up taking an existing solution and modifying it to what your company actually needs.
[00:06:22] Customer: You cannot throw away the legacy logging system and all its requirements, so you build adapters between the existing solution and everything else.
[00:06:32] Customer: So the idea is a project with a plugin system where you can just build what you need.
[00:06:46] Customer: Does it make sense, and did I answer your question?
[00:06:55] Guest: So the point of this project is the simplicity of creating new models for validation?
[00:07:03] Customer: Not models: the simplicity of creating new plugins for the gateway.
[00:07:09] Guest: By models I mean plugins.
[00:07:13] Customer: I don't want to use the word "model", because LLMs are usually called models, like GPT or Gemini models.
[00:07:13] Customer: It is better to say "plugins".
[00:07:30] Customer: Find the bare minimum we need: an agent connects to our gateway with authentication and other things, and then there is a standard outgoing connection to ChatGPT, Gemini, Claude, or something else.
[00:07:55] Customer: We don't care much about the fullness of coverage; we just want to get the idea.
[00:08:08] Customer: Then build it out as plugins, create a set of plugins people can use right away, and let them create other plugins based on those.
[00:08:27] Guest: Is it supposed to just decline the request if it contains private code or personal data, or what should happen?
[00:08:40] Customer: It depends on the plugin you write.
[00:08:40] Customer: We want to write a system that enables those plugins.
[00:08:52] Customer: Here is the problem: each company is very different, and existing gateways force you into using their system.
[00:09:10] Customer: Or they are closed source, and then they give you what they give you and charge you for it.
[00:09:19] Customer: The difference I hope to get is that a company can look at the system and easily add or replace the plugins it needs.
[00:09:36] Customer: One company says that somebody is not supposed to use it, and bans them.
[00:09:36] Customer: Another company not only bans them but logs what they tried to do, or allows it and then logs and flags it.
[00:09:36] Customer: That should be configurable.
[00:10:00] Customer: Does that make sense?
[00:10:02] Guest: Yes.
[00:10:10] Guest: There are always limits on what plugins can do.
[00:10:10] Guest: Should a plugin be able to analyze not only the request but also the response from the LLM, for example to exclude some data from it?
[00:10:31] Customer: Yes, definitely both request and response.
[00:10:37] Customer: That's one of the main things I hear companies asking for: what was the response?
[00:10:43] Customer: They use that data to analyze which model is better, because when they switch models there is no other way to see whether it got better or worse, for example in the wordiness of responses.
[00:11:09] Customer: So companies very often want to log responses as well, while some don't care.
[00:11:14] Customer: But they definitely should be able to see everything that comes in and everything that comes out of the model.
[00:11:31] Guest: What about routing?
[00:11:31] Guest: Should the gateway also be able to choose a model suitable for a request?
[00:11:45] Customer: That would be good.
[00:11:51] Customer: There is a model, not a large language model, I think it's called [inaudible], that classifies requests very nicely.
[00:12:12] Customer: One approach is to use it to see what kind of request you got and decide which model to use.
[00:12:21] Customer: For example, you don't need to spend money on the smartest model if you just need to find something in logs; a cheap model can do it.
[00:12:41] Customer: In order of priority, first comes intercepting the user request and being able to plug into it.
[00:13:00] Customer: Second is what comes out of the LLM.
[00:13:00] Customer: Third is the ability to route requests, or to configure routing and write routing plugins.
[00:13:23] Guest: What about installing plugins?
[00:13:23] Guest: Is it acceptable to restart the gateway after that?
[00:13:32] Customer: I think that's fine.
[00:13:38] Customer: I don't think it's a good idea to add things on the fly, because it's a server-side program and you should be careful what gets executed there.
[00:13:56] Customer: A better way is to stop it, create another instance, and reload it through some kind of process.
[00:14:03] Customer: We don't need to do it on the fly; that would add unnecessary complexity and security risks.
[00:14:22] Customer: The DeepSeek plugin system for its agent harness does load plugins on the fly, but you run it locally, on your own machine, so you know you added a plugin.
[00:14:43] Customer: No other user will be surprised that something changed.
[00:14:50] Customer: Since this is server-side, with lots of users connecting, it's okay to stop and restart the system.
[00:15:11] Guest: So the plugins will be generated by coding agents, right?
[00:15:16] Customer: I think so, though you can write them by hand if you want.
[00:15:22] Guest: What about tests for these plugins?
[00:15:22] Guest: Should they also be generated by AI?
[00:15:31] Customer: I think that's how it will be done.
[00:15:38] Customer: The idea of the system is that we provide something an IT department can take and add plugins to, depending on what they do.
[00:15:51] Customer: If they don't like tests, that's fine; if they wrote and installed a bad plugin, that's their problem.
[00:16:02] Customer: If they want to write tests by hand, it's up to them, but probably those will be written by AI as well.
[00:16:02] Customer: We can't force them to write tests.
[00:16:31] Guest: I think that's all for my questions.
[00:16:31] Guest: I have some additional ones, but they are not necessary.
[00:16:39] azamatbayramov: I have questions too.
[00:16:39] azamatbayramov: First, I want to verify that I understood correctly.
[00:16:51] azamatbayramov: Do you expect this server to hold API tokens for the LLMs, or will it just proxy requests from user computers with their own LLM tokens?
[00:17:12] azamatbayramov: In other words, will the server be the source of access to the LLM, or will it just proxy requests made with the users' own access?
[00:17:23] Customer: That's a very good question, and a pretty important one.
[00:17:28] Customer: I envisioned that it will contain the tokens, because I was thinking of such a system for a company.
[00:17:49] Customer: You probably have corporate accounts and tokens for the cloud providers, and you don't want to give them to everyone.
[00:18:05] Customer: There are so many LLMs and services, and the relationship between your business and each LLM provider can be very different.
[00:18:18] Customer: So I assumed the server will also contain the tokens, and IT departments will install and maintain them.
[00:18:30] Customer: On the other hand, access to the server will probably require authentication from the client side.
[00:18:41] Customer: For example, [redacted], [redacted] and [redacted] can access our system but can only use DeepSeek, or they can use Claude but only the cheapest model.
[00:19:06] Customer: [redacted] can use all the models they want.
[00:19:12] Customer: That's the way I envisioned it.
[00:19:20] Customer: Also try to assess what is possible, because the client's vision and what you can actually deliver can be very different.
[00:19:35] Customer: I would be happy if that functionality was configurable: you may provide a very simple login that can be extended to more complex cases.
[00:19:49] Customer: But you're right, we should think about token storage.
[00:20:02] Customer: Usually you don't store tokens on the server; you contact some kind of token management system via an API.
[00:20:23] Customer: But we can make it simple as well: store them on the system and put a big security warning about storing tokens.
[00:20:36] azamatbayramov: Thank you.
[00:20:36] azamatbayramov: Should we also give users the option to use their own tokens?
[00:20:36] azamatbayramov: For context, I already have some experience with LLM gateways because I work at [redacted].
[00:20:52] azamatbayramov: Not long ago an LLM gateway appeared there, and it is used the way our project describes.
[00:21:08] azamatbayramov: It checks whether personal data is being sent to LLMs like ChatGPT or Claude.
[00:21:14] azamatbayramov: In our case we use personal accounts: for example, I have a ChatGPT Pro subscription, and I use my account with my own harness through the corporate LLM gateway.
[00:21:35] azamatbayramov: This gives the company the opportunity to check the traffic and sanitize personal data.
[00:21:52] azamatbayramov: So should we give users the opportunity to go through the gateway with their own token?
[00:21:53] Customer: I think it's a valid use case, and you're right; I've seen it, and it amazes me to no end.
[00:22:06] Customer: Unless you give me some benefit, why would I connect through your servers and not directly to ChatGPT?
[00:22:17] Customer: And the benefit you offer me as a company is that you are going to be watching me.
[00:22:27] Customer: I'm glad you mentioned it; now I really want to use it.
[00:22:32] azamatbayramov: In our situation, otherwise security will come and bonk you on the head.
[00:22:40] Customer: But you see, that's why the service is needed.
[00:22:40] Customer: They do it not because it's good practice; they know it's a poor way of doing it.
[00:22:52] Customer: Doing it right is hard: collecting all the keys and routing everything.
[00:22:55] Customer: The other way is to have a pool of keys for which you create accounts.
[00:23:09] Customer: For example, you have 5 keys and 10 people, and you route through those keys round-robin or randomly; whether that's allowed depends on the cloud provider.
[00:23:36] Customer: People don't need to know those keys; they just access your system.
[00:23:36] Customer: That's the proper way of doing it.
[00:23:47] Customer: What you described is what people do because they don't have anything better.
[00:24:01] Customer: I guess we can add it as a feature, but I feel we would be building bad use cases into the system, and if we build them in, they will be used.
[00:24:24] Customer: Why encourage that behavior?
[00:24:37] azamatbayramov: Just to mention: in our company most people don't install Codex or Claude; they just install the company's platform agent.
[00:24:52] azamatbayramov: That agent automatically uses the LLM gateway, and it's fine for almost everyone, because they don't want to think about how to install things, use a VPN, or set up a proxy.
[00:25:12] azamatbayramov: It's comfortable to install one platform tool that already has all the company plugins and MCP servers.
[00:25:30] azamatbayramov: So in our situation it's not only about security; for most people it's about convenience.
[00:25:40] Customer: You're talking about agents, and that's a different thing.
[00:25:40] Customer: If you install an agent with all the keys built in and it does the right thing, you're right.
[00:25:52] Customer: But we're talking about a gateway, and there are different ways to solve this problem.
[00:26:04] Customer: You can solve it on the client side: you download the agent, a key is assigned when you download it, and you decide at that time.
[00:26:04] Customer: Or you decide at the gateway level.
[00:26:32] Customer: We can add it if you feel strongly.
[00:26:32] Customer: The system is supposed to be extendable, so if it exists, why not?
[00:26:50] azamatbayramov: At least security can always turn it off.
[00:26:53] Customer: Yes.
[00:26:55] Customer: [redacted], are you still with us?
[00:27:08] Guest: Yes.
[00:27:09] Customer: Any more questions?
[00:27:17] Guest: Which types of LLM API should we support?
[00:27:17] Guest: Any specific ones?
[00:27:23] Customer: Let's go with the standard ones.
[00:27:32] Customer: It would be nice if support for another API type was also a plugin that converts the format.
[00:27:32] Customer: That's the tricky part: you have to think about the format and how to convert it.
[00:27:53] Customer: I'm not aiming for breadth; we don't need to cover all of them, and one or two will be enough for me.
[00:28:09] Customer: I personally use Gemini, so I care about that one.
[00:28:09] Customer: As for standards, there is the OpenAI standard and some others I don't know.
[00:28:28] Guest: Claude, I believe.
[00:28:32] Customer: Yes, Claude.
[00:28:32] Customer: If we cover Claude and Gemini, that's fine.
[00:28:48] azamatbayramov: Do you have a preference for the language we develop the system in?
[00:28:48] azamatbayramov: For example, it would be strange to use Haskell, because it would be harder to create plugins.
[00:29:05] azamatbayramov: Is there a common language that is easy to understand and that agents write good code in?
[00:29:18] Customer: Any is fine, but I do have a preference: Python, if possible.
[00:29:27] Customer: Now that there are agents, I'm fine with JavaScript.
[00:29:27] Customer: I would strongly discourage Haskell.
[00:29:44] Customer: Python is good on the server side, especially for a plugin system, but you have to have Python on the server, and it's quite slow.
[00:30:07] Customer: For a big company its performance is probably not going to be the happiest thing, although you can write a pretty good system in Python with asynchronous code.
[00:30:20] Customer: If you want to write it in Rust, I won't complain too much, even though I'm not very familiar with Rust.
[00:30:32] azamatbayramov: Go?
[00:30:34] Customer: Go is fine.
[00:30:38] Customer: If you want to write it in C++, [inaudible].
[00:30:53] Customer: Rust is fine, Python is fine.
[00:30:57] Guest: What about Java?
[00:30:58] Customer: What's the point of writing these things in Java?
[00:30:58] Customer: There's no speed, there's no beauty.
[00:31:19] Guest: Many backend services do it.
[00:31:26] Customer: That's not a very good argument.
[00:31:26] Customer: I have nothing against Java; I've written code in Java.
[00:31:54] Customer: I would prefer to avoid Java and JavaScript, but if you only know JavaScript and are not comfortable with anything else, that's fine.
[00:31:54] Customer: Or Java; I will survive.
[00:32:18] Customer: So what languages are you planning to use?
[00:32:25] azamatbayramov: In our case, all of our teammates know Python.
[00:32:31] azamatbayramov: My own preference would be Go, because I work with it and love it, but it may be hard for other teammates.
[00:32:31] azamatbayramov: So I think we will prefer Python, but I don't know exactly yet.
[00:33:01] Customer: Go or Python are fine; approved.
[00:33:07] Customer: I understand why you would use Go, because of performance, and Python, because of extendability and the availability of developers.
[00:33:07] Customer: Those are good reasons.
[00:33:20] Customer: What about you, what do you think?
[00:33:28] Guest: For the gateway we'll use Java anyway, but for the plugin system we could use another language.
[00:33:39] Guest: I'm also thinking about developing our own domain-specific language for plugins, if we can.
[00:33:39] Guest: Maybe it is too hard; we'll figure it out.
[00:33:53] Customer: The problem with a new domain-specific language is that an LLM will have a hard time writing it; you'll need extensive documentation loaded into the context.
[00:34:08] Customer: It would be better to write in something LLMs already know how to write.
[00:34:18] Customer: Can you do it in Kotlin, at least?
[00:34:18] Customer: It compiles to Java bytecode.
[00:34:32] Guest: That could be complicated.
[00:34:32] Guest: Yes, I know what it is.
[00:34:36] Customer: So everyone on your team can write Java projects?
[00:34:42] Guest: Yes.
[00:34:43] Customer: In that case, fine.
[00:34:55] azamatbayramov: I have a question about the codebase and the process of creating new plugins.
[00:35:04] azamatbayramov: Would it be good to have instructions for coding agents, such as a skill for creating a plugin, an example, and an instruction?
[00:35:20] azamatbayramov: Then an agent would not have to learn the whole codebase to build plugins, which is harder and takes more context.
[00:35:36] azamatbayramov: What do you think about that?
[00:35:36] Customer: I think that would be good.
[00:35:36] Customer: That's the new age of programming: you have to write not just for programmers but for LLMs, so they know where to look things up.
[00:35:58] Customer: There are different ways to organize that knowledge, and you can ask agents to do it while they have the context.
[00:36:17] Customer: It would be nice to fit into my context window, so I don't have to send the entire project to Claude to figure out how it works and how to write plugins for it.
[00:36:34] Customer: I would say it's a nice-to-have feature, and it would be good practice.
[00:36:50] Customer: We have just a couple of minutes left.
[00:36:50] Customer: What is your first stage, something that works?
[00:36:50] Customer: When do you think you can deliver it, and how will it look?
[00:37:17] azamatbayramov: You're asking about the first version of our project, MVP zero?
[00:37:23] Customer: Yes, something people can take and run.
[00:37:23] Customer: It can be super simple: the simplest runnable thing.
[00:37:43] azamatbayramov: For us it's a proxy that gets a request from the user, adds a token stored, for example, in a .env file, sends it to one supported provider, and gets the result.
[00:38:01] azamatbayramov: Before sending, we may have a very simple plugin: if there are eight digits in a row, it's a phone number, so we mask it, send the request, and return the result to the user.
[00:38:21] Customer: When do you think you can deliver that: a week, two, three, ten?
[00:38:29] azamatbayramov: I think two weeks, maybe three.
[00:38:38] azamatbayramov: At the start I want to create basic rules for writing code, such as CI/CD and linters, so our code is consistent.
[00:38:59] azamatbayramov: Different teammates have different experience with Python, so it's worth creating infrastructure that supports good development later.
[00:39:18] azamatbayramov: So my approach is not to deliver as fast as possible, but to spend some time sharpening the axe first.
[00:39:38] Customer: Sharpen your saw, yes, excellent.
[00:39:58] azamatbayramov: I also have a question about the course itself, not the project.
[00:40:05] azamatbayramov: The statement was that we can use any AI tool for anything: research, writing, coding.
[00:40:24] azamatbayramov: If we are good users of agents, our work will be less about coding and more about validating what agents did and managing them; is that okay?
[00:40:48] Customer: Yes, that's how work is done now, and in this course we try to do it the same way it's done at the workplace.
[00:41:01] Customer: Now it's more important that you can build a product from the idea stage to a usable stage, and then improve it in stages: adding analytics, interacting with the client.
[00:41:30] Customer: For the rest there are agents, and we have to learn to be effective with them.
[00:41:30] Customer: Our role is now higher: it's more about product skills than programming skills.
[00:41:56] Customer: Two years ago I would have told you we're doing everything in Python because I know Python best; now I just ask an agent to write the Python code.
[00:42:15] Customer: So use it the way you would use it at work.
[00:42:26] Customer: That's one of the reasons your code has to be open-source-like.
[00:42:37] Customer: If it were closed source or for a company, managing this would be a nightmare: can you use an LLM or not, what are the licenses, did you break a non-disclosure agreement by sending material to Claude?
[00:43:10] Customer: So for learning we simplify it and make it kind of open source.
[00:43:10] Customer: You can use any license, as long as we don't have to deal with whether you can use an LLM.
[00:43:36] Customer: Otherwise a group that cannot send its code to Claude because of the license would be much slower than another group, and their results would be very different.
[00:43:58] Customer: We're learning to take a product from an idea and build it into something usable.
[00:44:09] Customer: I think you have a class in 12 minutes, right?
[00:44:14] Guest: Yes, but I have another question.
[00:44:14] Guest: How many plugins are expected to be installed in the gateway?
[00:44:23] Customer: That's a very good question.
[00:44:33] Customer: Can we have a million plugins?
[00:44:33] Customer: Depending on the answer, our plugin system has to be very different.
[00:44:47] Customer: I didn't have a number; I expected maybe a couple hundred.
[00:44:47] Customer: But why not a million?
[00:45:07] Customer: It would be cool if you looked at your architecture and said: for this architecture this is the upper limit, for example a hundred plugins, and past that things start slowing down because of some decision.
[00:45:30] Customer: If you add that analysis, that would be great; it should be part of the project.
[00:45:45] azamatbayramov: It's not that we have 100 plugins; it's that we can create 100 plugins in one hour.
[00:45:51] Customer: You can create them, but running them in the same system is different: how will your system handle messaging between plugins as a request passes from one to the next?
[00:46:10] Customer: You might not want to build a complicated system.
[00:46:10] Customer: For a 10-week course you might say you specifically picked this architecture, so it's 100 plugins running at the same time, and that's it.
[00:46:35] Customer: If you specify the limitation, that would be good, but it can be anything.
[00:46:35] Customer: I'm not looking for industrial-grade software at this point.
[00:46:46] Customer: This course prepares you for the industrial project next semester, in January.
[00:47:07] Customer: But it's good that you're thinking about it, because that's exactly what you should think about when writing for an industrial company.
[00:47:25] Customer: Any more questions?
[00:47:38] Customer: We're meeting next time on Friday, the same way and at the same time, right?
[00:47:46] Guest: Yes, I believe so.
[00:47:48] Customer: For everything else, write in the channel.
[00:47:48] Customer: I'll create a general channel for everyone, and project-specific questions can go in the project channel.
[00:48:01] Customer: The name of the second channel is probably somewhere in the notes; maybe you can post it in the channel so I don't have to look for it.
[00:48:28] Customer: Thank you very much.
[00:48:31] azamatbayramov: Thank you very much.
[00:48:32] Guest: Thanks for your time.
[00:48:36] Customer: I'm looking forward to seeing your products.
[00:48:36] Customer: It's going to be cool.
[00:48:43] azamatbayramov: Bye.
