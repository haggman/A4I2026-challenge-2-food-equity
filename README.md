# Challenge 2—Resilient Food Equity & Surplus Broker

**Agents for Impact 2026**

---

## Why this one matters

Somewhere in your city this afternoon, a grocer is going to throw away four hundred pounds of
perfectly good food. Not spoiled food—good food, with days left on it, that nobody happened to
buy. A farm will disc a field of squash back into the soil because the buyer cancelled. A
distributor will send a pallet of yogurt to landfill over a date code that means "best before,"
not "poisonous after."

And within a few miles of each of those, someone will skip dinner.

This is not a supply problem. Food that could be eaten is being thrown away a few miles from
people who need it. It is a **matching problem under a clock**, and the clock is the whole
difficulty. The grocer has four hours before the truck
goes to the compactor. The pantry two miles away could take every crate—if they knew it
existed, if they had somewhere cold to put it, and if someone could go and get it in time.

Most of the time nobody makes that match. Where it does happen it is usually a person with a
phone and a spreadsheet, or one of a handful of rescue platforms operating in a few cities—
because making the match requires knowing, in the same minute, what just became available, who
could use it, what they can physically store, and how long the food has left. That is four
questions, and by the time a human answers them the food is gone.

**Your job today is to build the thing that answers all four before the clock runs out.**

You'll build it for **one city**, not for everywhere. Which city is a real decision and it is
yours to make, but it will mean more once you know what you're building—so it comes a few
sections down rather than here.

---

## The four things you're working with

Small vocabulary, used consistently everywhere from here on. Worth thirty seconds now.

| Term | What it means |
|---|---|
| **Posting** | One offer of surplus, as a donor would actually type it: *"10 crates of spinach, harvested yesterday, needs cold storage."* Messy, free text, on a clock. This is the **query** side |
| **Recipient** | An organization that could receive it—a pantry, shelter, soup kitchen, clinic, diaper bank. Each has a written **profile** describing what it serves and what it can physically handle. These are the **corpus** you search |
| **Match** | A posting paired with a recipient, plus the reasoning: why them, what they can take, whether they can collect in time, and the message to send |
| **Track** | Which *kind* of surplus you specialise in. Changes the shape of the postings, not the machinery |

The whole challenge is: **posting in, ranked matches out, with a defensible reason attached.**

---

## Three tracks, one architecture

Every team building this challenge shares the same spine: one corpus of recipient
organizations, one embedding pass, one semantic search, one constraint filter, one drafted
handoff. **What changes between tracks is the shape of the offer, not the machinery.**

**These are suggestions, not a menu you're confined to.** Pick one, combine two, or invent
your own—if you can see a surplus-brokering problem in the same vein that these three miss, that
is exactly the kind of judgment this challenge rewards. Just be ready to say why yours is worth
solving.

| Track | What arrives | Who can take it | What makes it hard |
|---|---|---|---|
| 🛒 **Retail & grocer rescue** | Small, unpredictable, mixed—produce, dairy, prepared foods | Neighbourhood pantries, shelters, soup kitchens | Hours, not days. Many recipients have a domestic fridge or nothing |
| 🚜 **Farm & agricultural surplus** | Enormous, single-item—five tons of potatoes, a truckload of berries | Regional food banks with docks and warehouses | Almost nobody can take a load this size. Splitting it is its own problem |
| 🍼 **Critical non-food essentials** | Infant formula, diapers, temperature-sensitive supplies | Family shelters, clinics, diaper banks | Hard expiry, strict handling, and the narrowest set of qualified recipients |

Notice why this argues *for* the technology rather than around it. A rule-based system needs a
separate rulebook per track. A system that matches on meaning handles all three with one corpus
—which is exactly the claim you're being asked to prove.

---

## What you're building

**A broker.** Not a directory, and not a search box over a table of charities—an agent a
coordinator can hand a problem to at 4pm on a Thursday and get an actionable answer from.

Your coordinator isn't asking one question. Picture a single afternoon:

> **2:10pm, Thursday.** A grocer calls. They're pulling ten crates of spinach off the shelf—
> harvested yesterday, still good, but it has to leave their dock by 8pm and it has to stay
> cold the whole way. You have one afternoon and a group text full of volunteer drivers.

Over the next two hours the same coordinator asks all of these:

| What they ask | What answers it |
|---|---|
| *"Who can take ten crates of spinach and collect it before 8 tonight?"* | Vector search over recipient profiles, then filtered by storage and pickup window |
| *"Why them and not the big food bank downtown?"* | The profile text that drove the match, plus the constraints that eliminated everyone else |
| *"They said no. Who's next?"* | The ranked list below the top hit—which is why you return more than one |
| *"How long does spinach actually last once it leaves the store?"* | USDA shelf life, capped by the donor's own deadline |
| *"Can they collect it themselves, or do I need to send a driver?"* | `refrigerated_transport`, `pickup_window_hours`, `service_days` |
| *"Whose neighbourhood does this actually help?"* | Census tract demographics for the recipient's location |
| *"Write the message. I'll send it."* | Gemini, synthesising everything above |

Notice these need **different things**. Some need the semantic search. Some need only a filter.
One needs the agent to weigh a tradeoff and defend it. One needs it to write prose a human will
send under their own name.

**That range is the challenge.** An agent that only answers the first question is a search box.
An agent that handles all seven is something a coordinator would keep open all day.

### Questions that need more than we gave you

Be aware of the edges—and treat them as opportunity, because closing one is exactly what
separates a team.

| The question | What you'd need to add |
|---|---|
| *"Who's within a 20-minute drive?"* | Google Maps routing. We give you coordinates and straight-line distance |
| *"Plan the whole route for one van, five pickups"* | Multi-stop optimisation. A genuinely hard and genuinely impressive add-on |
| *"Is this product under recall?"* | [openFDA food enforcement API](https://open.fda.gov/apis/food/enforcement/)—CC0, and an agent that checks before brokering is a real safety feature |
| *"Has this recipient taken from us before?"* | Any persistence layer. Firestore is a natural fit and nothing in our stack covers it |
| *"Don't let two drivers claim the same pallet"* | Reservation state, which needs a transactional database—Firestore, AlloyDB, Cloud SQL or Spanner. BigQuery is an analytics warehouse and is genuinely the wrong tool for a claim/lock |
| *"Is this tract an official USDA food desert?"* | [USDA Food Access Research Atlas](https://www.ers.usda.gov/data-products/food-access-research-atlas/)—not in BigQuery, so you'd stage it yourself |
| *"A new pantry wants to join. Who writes their profile?"* | Nobody, today. See [Going further](#going-further)—this is the most interesting add-on available |

---

## Now pick your metro

**This is not a universal application. It is an application for one city**, and choosing
yours is the first real decision your team makes.

You do **not** have to pick the city you're sitting in.

Start here. These are tested end to end:

| Metro | Organizations | Households with no vehicle | Notes |
|---|---:|---:|---|
| **New York** | 363 | 45% | Highest no-vehicle rate in the country. Also the biggest: 363 organizations and 2,565 tracts, so every step takes longer |
| **Philadelphia** | 106 | 22% | Also has real published operational profiles |
| **Chicago** | 183 | 20% | The notebook default |
| **Atlanta** | 126 | 13% | |
| **Seattle** | 114 | 7% | Has **real** published operational profiles you can compare our generated ones against |
| **Dallas** | 173 | 6% | |
| **Houston** | 215 | 6% | Second-largest corpus |
| **Phoenix** | 114 | 6% | |
| **Denver** | 106 | 5% | Thinnest corpus of the nine, and the flattest vehicle-access signal |

Sorted by that second column, because it is the one worth reading before you choose. Vehicle
access is what makes food access different from plain poverty—if the nearest full grocery
store is three miles away, having no car is what turns a tight budget into an empty
refrigerator.

Notice that the list splits into two groups rather than sliding smoothly. Four metros sit at
20% and above; five sit at 13% and below, four of those clustered at 5–7%. In the second group
almost everybody drives, so vehicle access barely separates one neighbourhood from another and
your equity audit quietly collapses into "is this area poor"—which you could have measured with
income alone. That does not make those metros wrong. It makes them a harder place to find
something interesting, and worth knowing before hour three rather than after.

**We left Denver on the list on purpose.** It is worst on both axes—106 organizations, the
fewest of the nine, and 5% no-vehicle, the flattest signal—so it is the one metro here where
the data will genuinely fight you. That is a legitimate thing to build on if you go in knowing
it: with a smaller corpus your nine planted edge cases are about 8% of the search space rather
than 3%, which makes them easier to find and harder to dismiss, and an equity audit that comes
back with "this variable told us nothing here, and here is the evidence" is a better finding
than one that got lucky. Pick it deliberately or not at all.

One honest caveat about the column: it is the metro-wide rate, not the spread *within* the
metro, and spread is what an audit actually needs. The two usually travel together—a metro at
5% has almost nowhere with high numbers—but they are not the same thing.

All nine were run end to end and measured on 2026-08-08 from the published snapshot. The
no-vehicle figure is population-weighted across the metro's census tracts, so a 40-person tract
does not count the same as a 6,000-person one.

**Any US city will work**—the data is national. If you want one that isn't listed, **Appendix B
of the notebook** derives its bounding box for you and then tells you whether the city is worth
building on: how many organizations you'd get, and whether the need signals have enough spread
for your equity audit to find anything—it reports that spread directly, which is the number the
caveat above is about. It will tell you plainly if a city is a bad choice, which is cheaper to
learn now than at hour three.

> **Why US only?** Our socioeconomic layer is the American Community Survey, and the Canadian
> census has no equivalent vehicle-access variable. Toronto teams should pick a US metro and
> build there; the brokering logic is identical and it keeps every team's results comparable.
> If you want to continue afterward, ask a coach for the Canada appendix—Statistics Canada
> publishes an excellent deprivation index and a grocery-store proximity measure that is
> arguably better than anything we have here.

Then make the spinach call your own. The scenario above is ours; yours should name your city,
your donor, and your track:

> *"We coordinate food rescue in ______. A ______ has just offered us ______, and it has to move
> within ______. Here is who we'd have to call, and here is what we don't know about them."*

Write it down before you write code. Every design argument you have this afternoon—what to
embed, how to rank, what to cut—resolves faster against a specific situation than against a
general one, and it is the sentence your demo opens with.

---

## The technology you'll use

Every team, every challenge, uses the same core stack:

| | |
|---|---|
| **ADK** (Agent Development Kit) | You build your agent in Python with ADK. This is the frame everything hangs on |
| **Gemini** | The reasoning model—interpreting a messy posting, weighing two viable recipients, drafting the outreach |
| **BigQuery** | All the data lives here, and your agent queries it |
| **A managed MCP server** | Consume at least one—don't author your own. See below |
| **At least one tool you built** | A Python function tool, or a tool you defined yourself in MCP Toolbox. See below |
| **Deployed to Google Cloud** | Agent Runtime or Cloud Run, your choice. It has to actually run somewhere |

**Also already installed and worth ten seconds of your attention now rather than later: the
Antigravity CLI.** Type `agy` in Cloud Shell and you have a terminal coding agent that reads
your repo, proposes edits, and runs commands. It is not required and nothing here depends on
it, but every lane has tedious work it would happily absorb—ADK boilerplate, a Cloud Run deploy,
SQL against tables you just loaded. [Details in Step 3](#optional-but-encouraged-the-antigravity-cli).

### Choosing your MCP server

- **BigQuery's built-in MCP server**—quickest path if all you need is to query your tables.
- **[MCP Toolbox for Databases](https://github.com/googleapis/mcp-toolbox)**—Google's open
  source MCP server for databases. Prebuilt tools plus a framework for defining your own.

**The Toolbox is generally more flexible**, and if you want your agent's database access shaped
to your own tools rather than generic queries, start there.

> **Hint worth taking:** run the Toolbox as a container on **Cloud Run with minimum instances
> set to 1**. Cloud Run scales to zero by default, so the first request after an idle period
> pays a cold start—and the first request after an idle period is the one you make on stage.

### What "a tool you built" means, and why we ask

You could, in principle, do the entire semantic search through MCP Toolbox—it lets you define
a tool as parameterised SQL, so the `VECTOR_SEARCH` itself can be a Toolbox tool with no Python
at all. That's a legitimate design and we're not going to pretend otherwise.

**The requirement is one tool you designed, in either form.** What we're actually looking for is
the work that *isn't* a single query: turning a messy posting into a good search string, applying
constraint logic with judgment in it, assembling the Match Brief, drafting the outreach. That
tends to want Python. But if you can express it in Toolbox and defend the choice, that counts.

What doesn't count is consuming only prebuilt generic tools and calling that your design.

### And one required differentiator: **BigQuery vector search**

Each of the five challenges has one required technology. Yours is vector search, and here's why
it belongs in this problem rather than being bolted on.

Look at the two sentences again:

> *"10 crates of spinach, harvested yesterday, needs cold storage"*
> *"we serve 200 families, we have refrigeration, we need fresh greens"*

That is a perfect match and **they share no meaningful words.** "Spinach" is not "fresh greens."
"Cold storage" is not "refrigeration." Now make it worse: a third organization says *"hot meals
nightly, no cold storage."* A keyword search scores that one **highly**, because it contains the
exact phrase "cold storage"—as part of *not having any*.

You cannot fix this with better keywords. Every pantry writes their profile differently, and
there is no controlled vocabulary to normalise them to.

**So you embed the meaning instead.** Each organization's profile becomes a vector, the incoming
posting becomes a vector, and the match is a distance. Your agent must **call that search**—not
filter on categories, not `LIKE '%spinach%'`.

**But the search is not the answer, and this is the part most teams will miss.** One of the
organizations in your corpus wants fresh greens more than anything in the world and has **no
refrigeration at all.** Semantically it is a superb match. Operationally it is a pallet of
spoiled spinach and a coordinator who stops trusting your tool.

**Vector search is a candidate generator.** What you do afterward—storage compatibility, pallet
capacity, the pickup window against the clock—is where your agent earns its score.

---

## Getting started

You have **4.5 hours** and there are **8–10 of you**. That is too many people for one keyboard,
and the biggest risk to your team is the first hour disappearing into setup. Spend twenty
minutes on Step 0. It pays for itself twice over.

### Step 0—Organise your team

**Pick a team lead.** One person who makes the call when you're behind—and you *will* be behind.
Deciding in advance who says "we're cutting that" is worth more than it sounds.

**Pick a repo owner.** Can be the same person. They create the team's repository and add
everyone. Everything lands in one repo, not eight forks.

**Everyone else: create a free [GitHub](https://github.com) account now** if you don't have one,
and **send your username to the repo owner** while they're setting up.

**Agree your metro, your track, and your scenario** (see above). Five minutes. Write it where
everyone can see it.

**Then spend ten more on [Going further](#going-further).** It sits near the bottom because it
only makes sense once you know what you're building—but it is the section that decides whether
your demo looks like everyone else's, so read it before you write code rather than after.

**Split into four lanes.** All four start immediately, in parallel.

#### Data lane—2 to 3 people

Running the notebook takes a few minutes, so that is emphatically *not* the job. This lane owns
everything between raw tables and a match query the agent can call:

- **Build the embeddings.** `AI.EMBED` over `recipients.profile_text`, materialised into a
  table. **Do this first**—the agent lane is blocked until it exists. This is the equivalent of
  training a model in other challenges: it's an *input* to the agent, not a step 4.
- **Decide what text to embed.** We embed `profile_text`. Should you? Would folding in capacity
  or hours help, or would numbers wash out the meaning? Try both. This is a real experiment.
- **Decide how to compose the query.** Embed the raw posting, or enrich it first? Measure.
- **Build the constraint filter.** Storage compatibility, pallet capacity, pickup window
  against `hours_remaining`, service days. This is where the near-miss decoy gets caught.
- **Design the ranking.** Two viable recipients—bigger, closer, or higher-need tract? There is
  no right answer. Pick one and be able to defend it.
- **Hand the agent lane a working query early.** They need the exact SQL their tool will wrap.
- **The equity audit** ([explained below](#what-auditing-the-outcome-actually-means)).
- **Decide whether to bring extra data**, and if so, source it and check the licence.

#### Agent lane—2 to 3 people

- **Prompt engineering.** Expect this to be the hardest part. Your system instruction has to
  teach the agent who it's talking to, when to reach for which tool, what to do with a vague
  posting, and—importantly—**when to refuse.** An agent that confidently recommends a recipient
  who can't store the food is worse than one that says "nobody in range can take this."
- **At least one tool you built.** Required. The obvious one wraps the vector search. Python
  function tool or your own MCP Toolbox definition—both count, see above.
- **Decide what goes through MCP and what needs a custom tool.** Generic "query my tables" fits
  the managed MCP server. The match query, with its filters and ranking, usually wants a
  purpose-built tool. **This is your main coordination point with the data lane.**
- **Deploy early, not at the end.** Agent Runtime or Cloud Run. The front end is blocked on a
  live endpoint, and deployment always takes longer than you think.
- **Test with the real questions.** Take the seven coordinator questions above and ask them.
- **Decide what failure looks like.** What does your agent say when nothing matches, when the
  posting is unintelligible, when the only viable recipient is closed today?

#### Front end lane—2 people

Three routes. **Pick deliberately and be ready to say why**—the choice tells judges who you
think the user is.

| Option | Strength | Trade-off |
|---|---|---|
| **`adk web`** | Fastest. Built in. Works immediately, and it is where you should start | Obviously a developer tool. Fine while building, weak as a product story |
| **Gemini Enterprise** | Polished, almost no front-end code. An agent on Agent Runtime can be surfaced through it | Serves **internal** users, not the public |
| **Custom web UI** | Full control. A coordinator's queue with a clock ticking down beats a chat log | The most work by far. Scope it small |

**Everybody starts on `adk web`, and you should too**—it gets the agent lane unblocked in
minutes. The question is whether you *finish* there. Shipping `adk web` as your demo is a
choice you'll have to defend, and "it was already there" is the weakest version of that answer.

The Gemini Enterprise trade-off is worth thinking about rather than working around. Your user
*is* an internal one—a food-rescue coordinator at an organization, not a member of the public.
**Say that on purpose.** "We chose an internal-facing interface because our user is staff" is a
good answer. Discovering the limitation on stage is not.

- **Do not wait for a working agent.** Mock the response, build against it, swap later.
- **Whatever you build, the demo runs on it.** Test it on the machine you'll present from.

#### Story lane—1 to 2 people, starting at minute zero

Not "make slides at the end." This lane owns whether anyone understands what you built.

**What you're preparing: a short pitch deck and a quick demo.** Presentation time at this event
is tight—your facilitator will give you the number, but plan for short. **A crisp pitch with one
moment that lands beats a thorough walkthrough nobody has time to hear.**

- **The pitch deck.** Short. The problem, your scenario, what your agent does, what you found,
  what you'd do next. Front-load it—assume you get cut off before your last slide.
- **The demo.** Pick one or two postings that best show what your agent can do, and **rehearse
  them.** Have a screenshot ready in case the live version misbehaves.
- **The Match Brief**—your output artifact (see below). Something a coordinator would actually
  receive.
- **The honest limitations.** Judges explicitly reward this. One line in the deck is enough.
- **Know which half of your data is real.** You will be asked. The answer is in the notebook and
  it's a good one—make sure whoever presents can give it.

Time the whole thing out loud at least once. Teams almost always run long.

### Your output artifact: the Match Brief

Whatever else your agent does, it should produce this—something a coordinator could act on
without asking a follow-up question:

- **Which organization**, by name, with its address
- **Why them**—what in their profile made them the fit, in a sentence a human would accept
- **What they can actually take**—against the pallet count and storage on offer
- **The clock**—how long the food has, whether they can collect inside it, and the margin
- **Who it helps**—the neighbourhood their location serves
- **The drafted outreach message**, ready to send
- **The next two options**, because the first one will sometimes say no

### Step 1—Create the team repository

**Repo owner only.**

1. At the top of this page, click the green **Use this template** button → **Create a new
   repository**. *(No button? Use **Fork** and tell a coach.)*
2. Name it after your team, choose **Public**, click **Create repository**.
3. **Settings → Collaborators** → add every teammate's GitHub username.
4. Paste the repo URL where everyone can see it.

### Step 2—Get into your Google Cloud project

**Your facilitator will tell you how to access your project. Follow those instructions**—they
vary by venue and they're the fastest path.

**There is one project per team.** You all share it, which is the point—you can all see the same
BigQuery tables. It also means you can overwrite each other. Agree on who creates what.

You have Owner. You don't need to create a project, set up billing, or download a key file.

### Step 3—Everyone: get into Cloud Shell

**Cloud Shell is where you'll work.** It has `gcloud`, `bq`, Python, Node, git, Docker, and the
Antigravity CLI already installed. Nothing to set up on your laptop, no admin rights needed.

1. In the Google Cloud console, click the **terminal icon (`>_`) in the top right**. Use that
   icon rather than a bookmark or typed address: it opens Cloud Shell attached to *this*
   project, in *this* browser session. Typing a URL can land you in a different window signed in
   as a different account, which is a confusing twenty minutes nobody needs.

2. Clone your team's repository:

   ```bash
   git clone https://github.com/YOUR-TEAM/YOUR-REPO.git
   ```

3. Open the whole repo in the editor:

   ```bash
   cloudshell workspace .
   ```

   That opens your cloned folder as a workspace in the Cloud Shell Editor—the same as
   **File → Open Folder** in VS Code, which is essentially what the editor is.

New to any of this?
[Using Cloud Shell](https://cloud.google.com/shell/docs/using-cloud-shell)
·
[Cloud Shell Editor overview](https://cloud.google.com/shell/docs/editor-overview)

One thing worth knowing: your `$HOME` directory persists between sessions. Anything outside it
does not—so keep your work in the cloned repo.

**One repo, one branch per lane.** You're four lanes working in parallel in a single repository,
and if everyone commits to `main` you will spend part of your afternoon resolving conflicts
instead of building. Agree on this in Step 0 and it costs nothing:

```bash
git checkout -b agent      # or data, frontend, story
```

Merge to `main` when a lane has something the others need—the agent lane's endpoint, the data
lane's match query. Nobody needs a separate repository, and eight forks is the failure mode this
avoids.

#### Optional but encouraged: the Antigravity CLI

**`agy` is already installed in Cloud Shell.** You run zero setup commands—just type it.

Google would like you to try it. It is **not a requirement**, and nothing in this challenge
depends on it, so don't lose time fighting it if it isn't helping. But it's a genuinely capable
terminal coding agent: it reads your codebase, proposes edits with your permission, and runs
commands for you.

```bash
agy
```

Then talk to it in plain language. Where it tends to earn its keep here:

- **Agent lane**—scaffolding ADK boilerplate, wrapping a query in a tool, drafting a Cloud Run
  deploy. The tedious parts you already know how to do.
- **Data lane**—drafting the constraint filter SQL, or restructuring a query you've written.
- **Anyone, stuck**—paste an error and ask what's wrong. It can see your actual code.

`/diff` shows pending changes before you accept them, `/permissions` controls what it can do on
its own. Review before you accept—it's fast, which is exactly why it's worth reading what it did.

[Docs](https://antigravity.google/docs/cli/install)
·
[Hands-on codelab](https://codelabs.developers.google.com/antigravity-cli-hands-on)

### Step 4—Load the data

**Data lane's job.** One person runs it; nobody else waits.

1. In the Google Cloud console, search for **Colab Enterprise** and open it.
2. **You'll be asked to enable some APIs. Say yes.** Then the Colab Enterprise home page shows
   *another* **Enable APIs** button at the top. Click that too. Two prompts is expected—it isn't
   an error and you haven't done anything wrong.
3. **My Notebooks** → **Import** → source **URL**, and paste this:

   ```
   https://raw.githubusercontent.com/haggman/A4I2026-challenge-2-food-equity/main/notebooks/c2_01_load_explore.ipynb
   ```

   *(If your team modifies the notebook later, get your own copy's raw URL by opening the file
   on GitHub and clicking **Raw**.)*

4. Click **Import**, open the notebook, set `METRO` at the top, and run the cells top to bottom.

**Read the text between the cells.** Several explanations will save you time later, and one of
them—which half of the recipient data is real—is something judges will ask you about directly.

**If the notebook won't run**, there's a headless fallback. From the repo root in Cloud Shell:

```bash
bash scripts/load.sh chicago
```

```bash
bash scripts/load.sh --list       # every metro we've published
```

**One asymmetry worth knowing.** The notebook builds your data live, so it works for *any*
metro. The fallback loads a pre-built snapshot, so it only covers the metros we published in
advance—run `--list` to see them. If your metro isn't there and the notebook won't run, tell a
coach rather than switching cities to suit the tooling.

Invoke it with `bash` rather than `./scripts/load.sh`—that way it doesn't matter whether the
file arrived with its executable bit set.

It's safe to run more than once. Every table is fully replaced rather than appended to.

### What you'll have

Four tables in your project, in a dataset called `a4i_food`:

| Table | What it is |
|---|---|
| `recipients` | Every food-capable organization in your metro—typically 150–400—with profiles, storage, capacity, pickup constraints, and each organization's **real reported revenue** |
| `surplus_postings` | Ten surplus offers across the three tracks—your query side |
| `shelf_life` | USDA shelf life for 661 products, in hours |
| `tract_demographics` | Poverty, vehicle access, and assistance rates by census tract |

---

## The data, and why we chose it

**Be clear about this, because you'll be asked and the honest answer is a good one.**

**The organizations are real.** They come from the IRS **Exempt Organizations Business Master
File**—1.98 million tax-exempt organizations, published monthly by the federal government, in
the public domain under 17 U.S.C. § 105. We filter to the NTEE codes that identify food banks,
pantries, soup kitchens, nutrition sites, shelters, and community clinics. Real names, real
addresses, real classification, and each organization's **real reported annual revenue**.

**The operational details are generated, and they had to be.** Whether a pantry has a walk-in
cooler, how many pallets they can take, when they can collect—**none of that is public for any
organization in the United States.** It isn't hidden; nobody has ever collected it centrally.

So we generate it, and the notebook shows you exactly how: fourteen archetypes, phrasing modelled
on **real** published profiles from Seattle/King County and Pennsylvania (both public domain),
Their reported revenue does real work here rather than just sitting in a column: it places each
organization inside its archetype's range, so a regional operation and a storefront pantry come
out at genuinely different scales instead of drawing from the same dice. Roughly a third of them
report a figure—the rest file a postcard return that carries none, which we treat as *unknown*
rather than as *small*, because those are different things.

The rest is generated, and the notebook shows you exactly how: fourteen archetypes, phrasing
modelled on **real** published profiles from Seattle/King County and Pennsylvania (both public
domain), and generation seeded from each organization's tax ID so the same organization always produces
the same profile for every team.

**The clock is real.** USDA FSIS **FoodKeeper**, CC0, pinned in `data/`—661 products with shelf life by storage
state. Worth knowing its limits: it's consumer home-storage guidance for freshness and quality,
not a commercial cold-chain model. Right order of magnitude, wrong instrument for a guarantee.

**The need signal is real.** American Community Survey, via BigQuery public datasets.

### One thing we deliberately excluded, and why it's different here

Every challenge in this pack excludes race and ethnicity as a model input, and requires them
instead as an audit of the output. This is consistent with Google's own responsible-AI guidance.

The reasoning: race genuinely does correlate with food insecurity—that's well established and
you shouldn't pretend otherwise. But the correlation is a **proxy**. The causal variables are
economic and structural: income, vehicle access, distance to a grocery store. Those we can
measure directly, and they're in your data.

**But your challenge has no model inputs.** You embed *text*. There is no column to drop—whatever
is in a profile is in the vector permanently.

So the decision isn't what to drop. **It's what goes into the text.** And the line we drew:

> **An attribute that describes an operational constraint belongs in the profile.**
> **An attribute used to rank who deserves the food does not.**

*"We serve a halal-observant community and cannot accept pork"* is a hard matching constraint. A
broker that ignores it ships a pallet that gets thrown away. Same for language, infant nutrition,
medically restricted diets. **Excluding those would build a worse and less respectful system,
not a fairer one.** What doesn't belong is demographic composition used as a priority signal.

### What "auditing the outcome" actually means

Three steps, about twenty minutes, and most teams will skip it.

1. **Run your matcher across all ten postings** and collect the recipients it chose.
2. **Look up the tracts those organizations sit in** and pull demographics from
   `tract_demographics`.
3. **Compare to the metro as a whole.** Poorer than average, or richer? Higher or lower vehicle
   access?

Then say the answer out loud: **did the food go where the need is, or where the loading docks
are?**

Both answers are worth having. If your matches skew toward high-poverty, low-vehicle tracts, you
have evidence your system finds real need—say so, with numbers. If they skew the other way,
you've found something more interesting: **your matcher may be optimising for logistics
capability, because large organizations write more detailed profiles and sit in industrial
areas.** That is a real, subtle failure mode, it is probably happening, and presenting it
honestly will land better than a slide claiming everything worked.

---

## Going further

Everything above is what your agent has to do. Everything below is optional, and it is where
the difference between two teams actually shows up.

---

### What will set yours apart

Every team building Challenge 2 gets the same organizations, the same corpus, the same
technology. **The core is not where you win.**

Spend fifteen minutes deciding what *your* version does that nobody else's will:

- **Solve the "they said no" problem.** Everyone will build a top-1 match. Almost nobody will
  build the graceful second and third option, or the agent that learns a recipient declined and
  routes around them. Coordinators live in that world.
- **Split a load nobody can take whole.** Five tons of potatoes has no single recipient. An
  agent that proposes a three-way split with three drafted messages is doing something real.
- **Make the clock visible.** A match that arrives with "this has 6 hours left, they can
  collect in 2, here's your margin" is a different product from one that returns a name.
- **Break ties on something defensible.** Two recipients will often be equally viable. You have
  `reported_income` (real), `weekly_households`, and the need profile of the tract they sit in.
  Picking one deliberately and being able to say why beats returning whichever the search
  happened to rank first.
- **Take the equity audit seriously** instead of as a footnote. It's the most interesting
  conversation available in this challenge and most teams will skip it.
  ([What that means, concretely](#what-auditing-the-outcome-actually-means).)
- **Bring a dataset nobody else has**—your city's actual pantry directory, a transit feed, a
  recall API. (See [Bringing your own data](#bringing-your-own-data)—check the licence first.)

Read [how you'll be judged](#how-youll-be-judged) *before* you decide. It's at the bottom, it
takes two minutes, and it will change what you build.

---

### The add-on we'd build if we had another four hours

The data section above admits something: **the operational half of every recipient profile is
generated, because that information is not public for any pantry in the United States.** Not hidden—simply never collected. A pantry knows whether it has a walk-in
cooler. Nobody has ever asked all of them at once.

So build the thing that asks.

**An intake agent.** A coordinator at a new pantry talks to it, and it produces the structured
profile your matcher needs. Not a form—a conversation. Because a form gets you *"large fridge,"*
and an agent hears *"we've got a fridge and a chest freezer out back"* and asks the follow-up
that actually matters: **can you take a pallet, or does it need to come in by hand?** That
single distinction decides half the matches in this challenge, and no dropdown will ever
capture it.

Why this is worth your time rather than just worthy:

- **It closes the loop on our stated limitation.** We told you the data doesn't exist. You went
  and got it. That is a genuinely strong thing to say in a demo.
- **Its output feeds your differentiator directly.** The agent writes `profile_text`. Embed it
  and the new organization is searchable immediately—a pantry can register and receive a match
  in the same demo. That's a complete loop, and it's a much better closing beat than a table.
- **It is cheaper than it looks.** Intake is a handful of writes a day with nobody competing
  for the same row, so appending to BigQuery is fine. **Don't confuse this with the reservation
  problem**—two drivers claiming the same pallet in the same second is what needs a
  transactional database. Registering a pantry is not.

A lighter variant if you're short on time: point the agent at an organization's existing
website and have it draft the profile for a human to confirm. Same idea, far less typing, and
it scales to the whole city.

---

## Bringing your own data

**You're not limited to what we provide.** If your team knows a dataset that would make this
better—your city's actual pantry directory, a transit feed, a recall API—bring it. Thoughtful
sourcing is exactly the judgment this challenge rewards.

**Augment, don't replace.** Get the core working first. "Let's find better data" is one of the
most reliable ways to lose ninety minutes and have nothing to demo.

**Check the licence before you load it.** This is a publicly branded event and winning projects
get promoted. Anything you bring has to clear the same bar we applied to ourselves:

| | |
|---|---|
| ❌ No **NonCommercial** (NC) | Winners are promoted commercially |
| ❌ No **NoDerivatives** (ND) | Building on the data is the whole point |
| ❌ No **share-alike** (ODbL, CC BY-SA) | It would encumber what *you* build |
| ❌ No **individual-level personal data** | Aggregate public statistics only |
| ❌ No **unstated licence** | No licence means no rights granted |
| ✅ Public domain, CC0, US Government works | Safe |

**The trap most likely to catch you on this challenge:** the big national pantry directories—the
ones that come up first when you search—are **all rights reserved**, and at least one explicitly
forbids reproduction. We checked; that's why we're using the IRS file instead. If you're unsure,
ask a coach. Thirty seconds of checking beats finding out later.

**And one that's specific to you:** if you scrape a real pantry directory, you now hold contact
details for real people at real organizations. Think about whether your agent should be drafting
emails to them.

---

## What's in this repository

```
notebooks/c2_01_load_explore.ipynb   The main artifact. Run this first.
scripts/load.sh                      Headless fallback if Colab is unavailable.
data/profile_components.json         The vocabulary banks used to generate profiles.
                                     Read it—you should be able to inspect generated data.
data/foodkeeper.json                 USDA shelf-life data (CC0), pinned. See below.
agent/                               Empty. Your agent goes here.
```

**Why `foodkeeper.json` is committed rather than downloaded:** both USDA hosts return the file
happily in a browser and `403 Forbidden` to a notebook, because federal sites reject datacenter
IP ranges and every Colab runtime lives in one. The file is public domain and has not changed
since 2018, so pinning it removes an event-day dependency on a server that can decide it does
not like us. Worth remembering if you go looking for your own government data today: *"the data
is public"* and *"I can fetch it from my code"* are different claims.

`agent/` is empty on purpose. We built the on-ramp—real organizations, an honest corpus, a
clock, a need signal, and validation. We didn't build the vehicle. The design decisions in your
agent are what you'll be judged on.

---

## How you'll be judged

**"Finished" is not the goalpost.** Almost nobody completes everything they set out to do in 4.5
hours—that's the design, not a failure. A team that gets three quarters of the way with clear
reasoning and honest limitations will beat a team that demos something polished and hollow.

| Dimension | Weight | The question judges are asking |
|---|---:|---|
| **Impact & insight** | 30 | Would a coordinator actually use this? Is the match specific enough to act on? |
| **Technical execution** | 30 | Does it work, and is vector search genuinely used rather than name-checked? |
| **Rigor & judgment** | 25 | Can you defend the decisions you made along the way? |
| **Craft & communication** | 15 | Does the short pitch land, does the quick demo work, can you justify your interface? |
| **Bonus—range** | **+10** | Technology breadth and ambition that *serves* the solution |

Bonus sits **on top** of the 100, so ambition can't cannibalise the core. Nail the fundamentals
and add nothing, and you can still win. Wire up five services with no coherent match, and you
can't win on breadth alone.

### What "Rigor & judgment" actually means

This is the one teams under-invest in, because it's least visible in a demo. It's a quarter of
your score and the easiest place to stand out. Four concrete things:

**Data decisions you can defend.** Which half of your recipient data is real? (You were told.
Make sure whoever presents knows.) If you brought your own dataset, do you know its licence?

**Validation.** Did you check your tables before building, or assume no error meant no problem?
The notebook ships a validation section—using it, and saying what it told you, counts.

**Bias handling.** What went into your embedded text, and why? Did you run the
[equity audit](#what-auditing-the-outcome-actually-means)? Bring the numbers, not the intention.

**Knowing what your system can't do.** The operational profiles are generated. The shelf life is
consumer guidance, not cold-chain science. Locations are ZIP-level, not geocoded. A team that
volunteers its limitations shows more skill than one that oversells—and judges are told to
reward it.

One warning worth internalising: **if your top match is always right, you probably aren't
filtering.** There is at least one organization in your corpus that semantically looks perfect
and physically cannot store the food. If you never notice it, your pipeline isn't doing the
work—and a judge who asks "show me a case where the search was wrong" will find it in a minute.

### A note on decisions generally

Several places in this challenge ask you to choose rather than follow instructions—which metro,
which track, what text to embed, how to rank two viable recipients, what to cut when you're
behind. **None of those have a single right answer, and judges are not checking them against a
key.** They're asking whether you made the choice on purpose and can say why.

---

## Getting help

Ask a coach. That's what they're there for, and whatever you're stuck on has probably already
been solved at another table.

To report a problem with the data or the notebook, run the **diagnostic cell** at the bottom of
the notebook and share what it prints. One block, everything a coach needs, beats a screenshot
every time.
