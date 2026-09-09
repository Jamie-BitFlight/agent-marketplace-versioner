import { readFileSync } from "node:fs";

export default async function postCoverageSummary({ github, context }) {
  const xml = readFileSync("coverage-reports/coverage.xml", "utf8");
  const match = xml.match(/line-rate="([^"]+)"/);
  const coverage = match ? `${(parseFloat(match[1]) * 100).toFixed(2)}%` : "N/A";
  const comments = await github.rest.issues.listComments({
    owner: context.repo.owner,
    repo: context.repo.repo,
    issue_number: context.issue.number,
  });
  const existing = comments.data.find(
    (comment) => comment.user?.type === "Bot" && comment.body.includes("Test Coverage"),
  );
  const body = `## Test Coverage Report\n\n**Coverage:** ${coverage}\n\nCoverage XML available as artifact: \`coverage-xml\``;

  if (existing) {
    await github.rest.issues.updateComment({
      owner: context.repo.owner,
      repo: context.repo.repo,
      comment_id: existing.id,
      body,
    });
  } else {
    await github.rest.issues.createComment({
      owner: context.repo.owner,
      repo: context.repo.repo,
      issue_number: context.issue.number,
      body,
    });
  }
}
