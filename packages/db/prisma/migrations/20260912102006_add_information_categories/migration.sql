-- CreateEnum
CREATE TYPE "InformationCategory" AS ENUM ('memories_stories', 'photos_videos', 'voice_recordings', 'health_medical', 'financial', 'legal_official', 'relationships_family', 'career_work', 'beliefs_values', 'traditions_recipes', 'advice_wisdom', 'general');

-- AlterTable
ALTER TABLE "access_rules" ADD COLUMN     "allowed_content_types" JSONB,
ADD COLUMN     "allowed_information_categories" JSONB;

-- AlterTable
ALTER TABLE "knowledge_entries" ADD COLUMN     "category" "InformationCategory";
