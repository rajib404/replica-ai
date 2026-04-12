import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

async function main() {
  console.log('Seeding database...');

  const owner = await prisma.owner.upsert({
    where: { email: 'alex@replica-ai.dev' },
    update: {},
    create: {
      name: 'Alex',
      email: 'alex@replica-ai.dev',
      phone: '+1-555-0100',
      preferredLanguage: 'en',
    },
  });

  console.log(`Created owner: ${owner.name} (${owner.id})`);

  const cloudInstance = await prisma.modelInstance.upsert({
    where: { id: 'seed-cloud-instance' },
    update: {},
    create: {
      id: 'seed-cloud-instance',
      ownerId: owner.id,
      instanceType: 'cloud',
      hostname: 'replica-cloud-1.fly.dev',
      status: 'active',
      version: '0.1.0',
    },
  });

  console.log(`Created cloud instance: ${cloudInstance.hostname} (${cloudInstance.id})`);

  const localInstance = await prisma.modelInstance.upsert({
    where: { id: 'seed-local-instance' },
    update: {},
    create: {
      id: 'seed-local-instance',
      ownerId: owner.id,
      instanceType: 'local',
      hostname: 'alexs-macbook.local',
      status: 'active',
      version: '0.1.0',
    },
  });

  console.log(`Created local instance: ${localInstance.hostname} (${localInstance.id})`);

  console.log('Seeding complete.');
}

main()
  .then(async () => {
    await prisma.$disconnect();
  })
  .catch(async (e) => {
    console.error(e);
    await prisma.$disconnect();
    process.exit(1);
  });
