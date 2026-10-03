// Public template only. Never put private values in this tracked file.
// Build instructions and the private JSON schema are in submission-checklist.md.
#let data = if "private-data" in sys.inputs {
  json(sys.inputs.at("private-data"))
} else { (:) }
#let final = sys.inputs.at("mode", default: "preview") == "final"
#let usernames = ("azamatbayramov", "ExFuseMe", "DeniBorsh", "iceberkut")
#let members = data.at("members", default: usernames.map(username => (
  username: username, name: "", email: "",
)))
#let sha = data.at("report_sha", default: sys.inputs.at("report-sha", default: ""))
#let recording = data.at("recording_url", default: "")
#let privacy = data.at("privacy_statement", default:
  "No private links, identity mapping, university emails or credentials are included in the revised public tree; a historical transcript remains with publication permission unconfirmed.")
#let transcript = data.at("transcript", default: "")
#if final {
  assert(sha.match(regex("^[0-9a-f]{40}$")) != none, message: "Supply the final full main SHA.")
  assert(members.len() == 4 and members.map(m => m.username) == usernames,
    message: "Supply the four verified team-member mappings in template order.")
  assert(members.all(m => m.name.trim() != "" and m.email.contains("@")),
    message: "Supply real names and university emails privately.")
  assert(recording.starts-with("https://"), message: "Supply the instructor-accessible recording URL privately.")
  assert(data.at("links_verified", default: false), message: "Verify the final report and private recording access.")
  assert(data.at("privacy_resolved", default: false), message: "Resolve historical transcript permissions and supply an accurate privacy statement.")
  assert(data.at("privacy_statement", default: "").trim() != "", message: "Supply an explicit accurate privacy statement.")
}
#if transcript != "" {
  assert(data.at("publication_refused", default: false) and data.at("private_sharing_permitted", default: false),
    message: "Include a transcript only after publication refusal and private-sharing permission.")
}
#let field(value) = if value == "" { text(fill: rgb("6b7280"))[Not supplied] } else { value }
#let report = "https://github.com/iteam7/gateway7/blob/" + sha + "/reports/week-01/README.md"
#set document(title: "Modular LLM Gateway Team 7 Week 01", author: "team 7")
#set page(paper: "a4", margin: 20mm, numbering: "1", number-align: center)
#set text(font: "DejaVu Sans", size: 10pt, lang: "en")
#set par(leading: 0.7em)
#set heading(numbering: none)
#show heading.where(level: 1): set text(size: 20pt, weight: "bold")
#show heading.where(level: 2): set text(size: 12pt, weight: "bold")
#show link: set text(fill: rgb("1e40af"))

= Modular LLM Gateway
Team 7 · Week 01 · Assignment 1
#if not final { block(inset: 8pt, fill: rgb("f3f4f6"))[
  *Draft preview - not ready for submission*
] }

== Team members
#table(
  columns: (1.05fr, 1.1fr, 1.5fr), inset: 7pt,
  stroke: 0.4pt + rgb("d1d5db"),
  fill: (x, y) => if y == 0 { rgb("f3f4f6") },
  table.header([*GitHub username*], [*Real name*], [*University email*]),
  ..members.map(m => (m.username, field(m.name), field(m.email))).flatten(),
)

== Public report
#if sha.match(regex("^[0-9a-f]{40}$")) != none {
  link(report)[Week 01 report at the selected commit]
  linebreak()
  text(size: 8pt)[#if final { [Commit: ] } else { [Preview baseline: ] }#sha]
} else {
  field("")
  text(" - select the final full main commit after review and merge.")
}

== Kickoff recording
#if recording != "" { link(recording)[Open the private kickoff recording] } else { field("") }

#if transcript != "" [
  == Meeting transcript
  #transcript
]

== Privacy
#privacy
#context assert(counter(page).final().first() <= 2, message: "The assignment wrapper must not exceed two pages.")
