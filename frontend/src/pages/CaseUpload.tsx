/**
 * File: src/pages/CaseUpload.tsx
 * Purpose: Form for an attorney to create a new case from a title and case facts (with an
 *   optional document input, cosmetic until real uploads land). Submits through lib/api.ts
 *   and returns to the dashboard.
 * Depends on: react-router-dom, @tanstack/react-query, lib/api.ts, components/ui/*
 * Related: backend/app/api/cases.py (POST /api/cases)
 * Security notes: case_facts is attorney work product — never log its contents. Here it only
 *   passes through the API function.
 */

import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import * as api from '@/lib/api';

export function CaseUpload() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [title, setTitle] = useState('');
  const [caseFacts, setCaseFacts] = useState('');

  const createCase = useMutation({
    mutationFn: () => api.createCase({ title, caseFacts }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['cases'] });
      navigate('/dashboard');
    },
  });

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    createCase.mutate();
  };

  return (
    <Card className="mx-auto max-w-2xl">
      <CardHeader>
        <CardTitle>New case</CardTitle>
        <CardDescription>
          Give the case a title and the facts your opponent will argue against.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="title">Case title</Label>
            <Input
              id="title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Rivera v. Coastal Logistics"
              required
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="caseFacts">Case facts</Label>
            <Textarea
              id="caseFacts"
              value={caseFacts}
              onChange={(event) => setCaseFacts(event.target.value)}
              placeholder="Summarize the dispute, the parties, and the key facts…"
              rows={6}
              required
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="documents">Supporting documents (optional)</Label>
            <Input id="documents" type="file" multiple disabled />
            <p className="text-xs text-muted-foreground">
              Uploads are wired up once the backend lands.
            </p>
          </div>
          {createCase.isError && (
            <p className="text-sm text-destructive">
              Could not create the case. Try again.
            </p>
          )}
          <div className="flex gap-2">
            <Button type="submit" disabled={createCase.isPending}>
              {createCase.isPending ? 'Creating…' : 'Create case'}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => navigate('/dashboard')}
            >
              Cancel
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
