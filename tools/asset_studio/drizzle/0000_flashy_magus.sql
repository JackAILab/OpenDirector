CREATE TABLE `iteration_requests` (
	`id` text PRIMARY KEY NOT NULL,
	`user_id` text NOT NULL,
	`case_id` text NOT NULL,
	`asset_id` text NOT NULL,
	`playhead` real DEFAULT 0 NOT NULL,
	`instruction` text NOT NULL,
	`status` text DEFAULT 'queued' NOT NULL,
	`paid_generation_allowed` integer DEFAULT false NOT NULL,
	`created_at` text NOT NULL
);
--> statement-breakpoint
CREATE INDEX `iteration_requests_owner_case_created_idx` ON `iteration_requests` (`user_id`,`case_id`,`created_at`);
