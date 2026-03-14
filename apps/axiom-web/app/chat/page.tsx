import Link from "next/link";

export default function ChatPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-8">
      <h1 className="text-2xl font-semibold">Chat</h1>
      <p className="text-zinc-500">Coming soon.</p>
      <Link
        href="/"
        className="text-sm text-zinc-500 underline hover:text-foreground"
      >
        Back to home
      </Link>
    </div>
  );
}
