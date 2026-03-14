"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
      <div className="flex flex-wrap items-center gap-3">{children}</div>
    </section>
  );
}

const scrollItems = Array.from({ length: 20 }, (_, i) => `Item ${i + 1}`);

export default function DesignPage() {
  const [inputValue, setInputValue] = useState("");
  const [textareaValue, setTextareaValue] = useState("");

  return (
    <main className="mx-auto max-w-4xl px-6 py-12 space-y-10">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Design System</h1>
        <p className="mt-1 text-muted-foreground">
          Kitchen-sink preview of shadcn/ui primitives.
        </p>
      </div>

      <Separator />

      {/* Button */}
      <Section title="Button">
        <Button>Default</Button>
        <Button variant="secondary">Secondary</Button>
        <Button variant="outline">Outline</Button>
        <Button variant="destructive">Destructive</Button>
        <Button variant="ghost">Ghost</Button>
        <Button variant="link">Link</Button>
        <Button disabled>Disabled</Button>
      </Section>

      <Separator />

      {/* Badge */}
      <Section title="Badge">
        <Badge>Default</Badge>
        <Badge variant="secondary">Secondary</Badge>
        <Badge variant="outline">Outline</Badge>
        <Badge variant="destructive">Destructive</Badge>
      </Section>

      <Separator />

      {/* Input */}
      <Section title="Input">
        <Input
          className="w-72"
          placeholder="Type something…"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
        />
        <Input className="w-72" placeholder="Disabled" disabled />
      </Section>

      <Separator />

      {/* Textarea */}
      <Section title="Textarea">
        <Textarea
          className="w-72"
          placeholder="Write a message…"
          value={textareaValue}
          onChange={(e) => setTextareaValue(e.target.value)}
          rows={4}
        />
      </Section>

      <Separator />

      {/* Card */}
      <Section title="Card">
        <Card className="w-80">
          <CardHeader>
            <CardTitle>Axiom</CardTitle>
            <CardDescription>Local-first RAG application.</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Store and query your documents with full local privacy.
            </p>
          </CardContent>
          <CardFooter className="flex justify-end gap-2">
            <Button variant="outline" size="sm">
              Cancel
            </Button>
            <Button size="sm">Save</Button>
          </CardFooter>
        </Card>
      </Section>

      <Separator />

      {/* Tabs */}
      <Section title="Tabs">
        <Tabs defaultValue="overview" className="w-96">
          <TabsList>
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="settings">Settings</TabsTrigger>
            <TabsTrigger value="logs">Logs</TabsTrigger>
          </TabsList>
          <TabsContent value="overview" className="mt-2">
            <Card>
              <CardContent className="pt-4 text-sm text-muted-foreground">
                Overview content goes here.
              </CardContent>
            </Card>
          </TabsContent>
          <TabsContent value="settings" className="mt-2">
            <Card>
              <CardContent className="pt-4 text-sm text-muted-foreground">
                Settings content goes here.
              </CardContent>
            </Card>
          </TabsContent>
          <TabsContent value="logs" className="mt-2">
            <Card>
              <CardContent className="pt-4 text-sm text-muted-foreground">
                Log entries go here.
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </Section>

      <Separator />

      {/* Dialog */}
      <Section title="Dialog">
        <Dialog>
          <DialogTrigger render={<Button variant="outline" />}>
            Open Dialog
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Confirm Action</DialogTitle>
              <DialogDescription>
                Are you sure you want to proceed? This action cannot be undone.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter showCloseButton>
              <Button>Confirm</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </Section>

      <Separator />

      {/* Dropdown Menu */}
      <Section title="Dropdown Menu">
        <DropdownMenu>
          <DropdownMenuTrigger render={<Button variant="outline" />}>
            Open Menu
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuLabel>Actions</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem>View</DropdownMenuItem>
            <DropdownMenuItem>Edit</DropdownMenuItem>
            <DropdownMenuItem>Duplicate</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="destructive">Delete</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </Section>

      <Separator />

      {/* Scroll Area */}
      <Section title="Scroll Area">
        <ScrollArea className="h-40 w-56 rounded-md border">
          <div className="p-3 space-y-1">
            {scrollItems.map((item) => (
              <div
                key={item}
                className="text-sm py-1 px-2 rounded hover:bg-accent cursor-default"
              >
                {item}
              </div>
            ))}
          </div>
        </ScrollArea>
      </Section>

      <Separator />

      {/* Tooltip */}
      <Section title="Tooltip">
        <Tooltip>
          <TooltipTrigger render={<Button variant="outline" />}>
            Hover me
          </TooltipTrigger>
          <TooltipContent>
            <p>This is a tooltip</p>
          </TooltipContent>
        </Tooltip>
      </Section>
    </main>
  );
}
